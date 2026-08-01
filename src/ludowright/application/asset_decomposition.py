"""Asset decomposition, dependency planning, and guided recommendations."""

from __future__ import annotations

import json
from collections.abc import Iterable
from contextlib import AbstractContextManager
from dataclasses import dataclass
from importlib import resources
from typing import cast

from pydantic import ValidationError

from ludowright.application.asset_registry import (
    DEFAULT_ASSET_REGISTRY_PATH,
    AssetRegistryNotFoundError,
    AssetRegistryService,
)
from ludowright.contracts import (
    AssetContract,
    AssetDecompositionContract,
    AssetDecompositionCorrectionContract,
    AssetDecompositionRecommendationCatalogContract,
    AssetDecompositionRecommendationRuleContract,
    AssetDecompositionReportContract,
    AssetDependencyContract,
    CaptureProfileRecommendationContract,
)
from ludowright.contracts.asset_decomposition import (
    CorrectionCode,
    CorrectionSeverity,
    DecompositionState,
)
from ludowright.domain import (
    AssetFamily,
    AssetId,
    CaptureSubjectMode,
    DependencyGraph,
    DependencyKey,
    DependencyNode,
    DependencyNodeKind,
    DependencyRelation,
    DomainValidationError,
    FreshnessState,
    FrozenJsonValue,
    InvalidationMode,
    RevisionVersion,
)
from ludowright.infrastructure import (
    DEFAULT_DEPENDENCY_GRAPH_PATH,
    DependencyGraphRepository,
    JsonDocumentRepository,
    ProjectFilesystem,
    RepositoryPath,
    StructuredDocumentRepository,
    YamlDocumentRepository,
)

_RECOMMENDATIONS_RESOURCE = "recommendations.json"
_DECOMPOSITION_LOCK = "asset-decomposition"
_SUBJECT_MODE_ORDER = {
    CaptureSubjectMode.ASSET: 0,
    CaptureSubjectMode.COMPONENTS: 1,
    CaptureSubjectMode.VARIANTS: 2,
    CaptureSubjectMode.STATES: 3,
}


class AssetDecompositionError(RuntimeError):
    """Base failure for decomposition and dependency planning."""


class AssetDecompositionValidationError(AssetDecompositionError):
    """Raised when guided corrections are required before persistence."""

    def __init__(self, message: str, report: AssetDecompositionReportContract) -> None:
        super().__init__(message)
        self.report = report


class AssetDecompositionRollbackError(AssetDecompositionError):
    """Raised when a graph write cannot be safely restored after a later failure."""


@dataclass(frozen=True, slots=True)
class AssetDecompositionResult:
    """Stable result shared by application callers and CLI renderers."""

    report: AssetDecompositionReportContract

    def as_data(self) -> dict[str, object]:
        """Return the published JSON-compatible report."""
        return cast(dict[str, object], self.report.model_dump(mode="json"))


class AssetDecompositionService:
    """Apply one complete decomposition through the registry and graph boundaries."""

    def __init__(
        self,
        filesystem: ProjectFilesystem,
        *,
        catalog: AssetDecompositionRecommendationCatalogContract | None = None,
    ) -> None:
        if not isinstance(filesystem, ProjectFilesystem):
            raise TypeError("asset decomposition requires ProjectFilesystem")
        self._filesystem = filesystem
        self._registry = AssetRegistryService(filesystem)
        self._graph_repository = DependencyGraphRepository(filesystem)
        self._catalog = catalog or _load_recommendation_catalog()

    def decompose(
        self,
        asset_id: str,
        *,
        input_path: RepositoryPath | None = None,
        dry_run: bool = False,
    ) -> AssetDecompositionResult:
        """Inspect or replace one asset decomposition deterministically."""
        canonical_asset_id = _canonical_asset_id(asset_id)
        if input_path is None:
            return self._inspect(canonical_asset_id)
        if not isinstance(input_path, RepositoryPath):
            raise TypeError("decomposition input requires RepositoryPath")
        with self._operation_lock(dry_run):
            return self._apply(
                canonical_asset_id,
                input_path=input_path,
                dry_run=dry_run,
            )

    def _inspect(self, asset_id: str) -> AssetDecompositionResult:
        current = self._current_asset(asset_id)
        graph_snapshot = self._graph_repository.load_optional()
        graph = graph_snapshot.graph if graph_snapshot is not None else DependencyGraph.empty()
        decomposition = _decomposition_from_asset(current, graph)
        recommendation, recommendation_correction = self._recommend(
            current,
            decomposition,
        )
        corrections = (recommendation_correction,) if recommendation_correction else ()
        return AssetDecompositionResult(
            report=_report(
                state="current",
                dry_run=False,
                asset=current,
                decomposition=decomposition,
                corrections=corrections,
                capture_profile=recommendation,
                registry_version=self._registry.inspect(asset_id).registry_version,
                dependency_graph_revision=graph.revision.value,
                valid=True,
            )
        )

    def _apply(
        self,
        asset_id: str,
        *,
        input_path: RepositoryPath,
        dry_run: bool,
    ) -> AssetDecompositionResult:
        current = self._current_asset(asset_id)
        registry_result = self._registry.inspect(asset_id)
        request = self._load_request(input_path)
        graph_snapshot = self._graph_repository.load_optional()
        graph = graph_snapshot.graph if graph_snapshot is not None else DependencyGraph.empty()

        if request.asset_id != asset_id:
            report = self._invalid_report(
                current=current,
                request=request,
                graph=graph,
                registry_version=registry_result.registry_version,
                dry_run=dry_run,
                correction=_correction(
                    code="input-asset-mismatch",
                    severity="error",
                    subject=request.asset_id,
                    message="the decomposition input targets another asset",
                    suggestion=f"set asset_id to {asset_id!r} or use the matching project asset",
                ),
            )
            raise AssetDecompositionValidationError(
                "decomposition input does not match the selected asset",
                report,
            )

        try:
            updated_asset = _replace_decomposition(current, request)
        except (DomainValidationError, ValidationError, ValueError) as error:
            report = self._invalid_report(
                current=current,
                request=request,
                graph=graph,
                registry_version=registry_result.registry_version,
                dry_run=dry_run,
                correction=_correction(
                    code="invalid-decomposition",
                    severity="error",
                    subject=asset_id,
                    message=str(error),
                    suggestion=(
                        "correct component hierarchy, IDs, statuses, and required-item rules"
                    ),
                ),
            )
            raise AssetDecompositionValidationError(
                "decomposition input violates the asset contract",
                report,
            ) from error

        assets = self._registry.list_assets().assets
        corrections = list(_dependency_corrections(asset_id, request.dependencies, assets))
        recommendation, recommendation_correction = self._recommend(
            updated_asset,
            request,
        )
        if recommendation_correction is not None:
            corrections.append(recommendation_correction)
        if any(item.severity == "error" for item in corrections):
            report = _report(
                state="invalid",
                dry_run=dry_run,
                asset=current,
                decomposition=request,
                corrections=tuple(corrections),
                capture_profile=recommendation,
                registry_version=registry_result.registry_version,
                dependency_graph_revision=graph.revision.value,
                valid=False,
            )
            raise AssetDecompositionValidationError(
                "decomposition requires guided corrections before persistence",
                report,
            )

        graph_changed = updated_asset != current or graph_snapshot is None
        try:
            planned_graph = _plan_graph(
                graph,
                asset_id=asset_id,
                asset_changed=updated_asset != current,
                dependencies=request.dependencies,
            )
        except (DomainValidationError, KeyError, ValueError) as error:
            correction = _correction(
                code="graph-reconciliation-required",
                severity="error",
                subject=asset_id,
                message=str(error),
                suggestion="refresh or reconcile the existing dependency graph before retrying",
            )
            report = _report(
                state="invalid",
                dry_run=dry_run,
                asset=current,
                decomposition=request,
                corrections=(*corrections, correction),
                capture_profile=recommendation,
                registry_version=registry_result.registry_version,
                dependency_graph_revision=graph.revision.value,
                valid=False,
            )
            raise AssetDecompositionValidationError(
                "dependency graph cannot accept this decomposition safely",
                report,
            ) from error

        graph_changed = graph_changed or planned_graph != graph
        if updated_asset == current and planned_graph == graph:
            return AssetDecompositionResult(
                report=_report(
                    state="planned" if dry_run else "current",
                    dry_run=dry_run,
                    asset=current,
                    decomposition=request,
                    corrections=tuple(corrections),
                    capture_profile=recommendation,
                    registry_version=registry_result.registry_version,
                    dependency_graph_revision=graph.revision.value,
                    valid=True,
                )
            )
        planned_registry_version = registry_result.registry_version + 1
        planned_report = _report(
            state="planned" if dry_run else "updated",
            dry_run=dry_run,
            asset=updated_asset,
            decomposition=request,
            corrections=tuple(corrections),
            capture_profile=recommendation,
            registry_version=planned_registry_version,
            dependency_graph_revision=planned_graph.revision.value,
            valid=True,
        )
        if dry_run:
            return AssetDecompositionResult(report=planned_report)

        prior_graph_bytes = _read_optional_bytes(self._filesystem, DEFAULT_DEPENDENCY_GRAPH_PATH)
        graph_written = False
        graph_after_bytes: bytes | None = None
        try:
            if graph_changed:
                if graph_snapshot is None:
                    self._graph_repository.create(planned_graph, timeout=5.0)
                else:
                    self._graph_repository.replace(graph_snapshot, planned_graph, timeout=5.0)
                graph_written = True
                graph_after_bytes = _read_optional_bytes(
                    self._filesystem,
                    DEFAULT_DEPENDENCY_GRAPH_PATH,
                )
            registry_update = self._registry.replace_contract(
                updated_asset,
                event_type="asset.decomposed",
                event_payload=_event_payload(request, recommendation, planned_graph),
                expected_asset=current,
                operation="decompose",
            )
        except BaseException as error:
            if graph_written:
                try:
                    _restore_graph(
                        self._filesystem,
                        prior_graph_bytes,
                        graph_after_bytes,
                    )
                except BaseException as rollback_error:
                    raise AssetDecompositionRollbackError(
                        f"asset decomposition graph rollback failed: {rollback_error}"
                    ) from error
            raise

        return AssetDecompositionResult(
            report=planned_report.model_copy(
                update={
                    "registry_version": registry_update.registry_version,
                    "state": "updated",
                }
            )
        )

    def _current_asset(self, asset_id: str) -> AssetContract:
        try:
            result = self._registry.inspect(asset_id)
        except AssetRegistryNotFoundError:
            raise
        if result.asset is None:
            raise AssetDecompositionError(f"asset does not exist: {asset_id}")
        return result.asset

    def _load_request(self, path: RepositoryPath) -> AssetDecompositionContract:
        repository: StructuredDocumentRepository[AssetDecompositionContract]
        if path.name.endswith(".json"):
            repository = JsonDocumentRepository(self._filesystem, path, AssetDecompositionContract)
        elif path.name.endswith(".yaml"):
            repository = YamlDocumentRepository(self._filesystem, path, AssetDecompositionContract)
        else:
            raise AssetDecompositionError("decomposition input must use .json or .yaml")
        try:
            return repository.load().value
        except ValidationError as error:
            raise AssetDecompositionError(
                f"decomposition input is not a valid asset-decomposition contract: {path}"
            ) from error

    def _recommend(
        self,
        asset: AssetContract,
        decomposition: AssetDecompositionContract,
    ) -> tuple[
        CaptureProfileRecommendationContract,
        AssetDecompositionCorrectionContract | None,
    ]:
        rule = _find_recommendation(self._catalog, asset.family, asset.subtype)
        if rule is None:
            recommendation = CaptureProfileRecommendationContract(
                state="unavailable",
                family=asset.family,
                subtype=asset.subtype,
                subject_modes=(CaptureSubjectMode.ASSET,),
                required_item_ids=(),
                reason=(
                    "no packaged capture-profile recommendation matches this family and subtype; "
                    "review the visual foundation before generating jobs"
                ),
            )
            return recommendation, _correction(
                code="profile-review",
                severity="warning",
                subject=asset.id,
                message="the decomposition has no matching capture-profile recommendation",
                suggestion="choose or define a versioned capture profile before visual production",
            )

        available = {CaptureSubjectMode.ASSET}
        if decomposition.components:
            available.add(CaptureSubjectMode.COMPONENTS)
        if decomposition.variants:
            available.add(CaptureSubjectMode.VARIANTS)
        if decomposition.states:
            available.add(CaptureSubjectMode.STATES)
        modes = tuple(
            mode
            for mode in sorted(rule.subject_modes, key=_SUBJECT_MODE_ORDER.__getitem__)
            if mode in available
        )
        required_item_ids = tuple(
            sorted(
                item.id
                for items in (
                    decomposition.components,
                    decomposition.variants,
                    decomposition.states,
                )
                for item in items
                if item.required
            )
        )
        recommendation = CaptureProfileRecommendationContract(
            state="recommended",
            profile_id=rule.profile_id,
            profile_version=rule.profile_version,
            family=asset.family,
            subtype=asset.subtype,
            subject_modes=modes,
            required_item_ids=required_item_ids,
            reason=(
                f"{rule.rationale} The profile key is a recommendation only; "
                "an executable profile catalog is a later visual-foundation slice."
            ),
        )
        return recommendation, None

    def _invalid_report(
        self,
        *,
        current: AssetContract,
        request: AssetDecompositionContract,
        graph: DependencyGraph,
        registry_version: int,
        dry_run: bool,
        correction: AssetDecompositionCorrectionContract,
    ) -> AssetDecompositionReportContract:
        recommendation, recommendation_correction = self._recommend(current, request)
        corrections = [correction]
        if recommendation_correction is not None:
            corrections.append(recommendation_correction)
        return _report(
            state="invalid",
            dry_run=dry_run,
            asset=current,
            decomposition=request,
            corrections=tuple(corrections),
            capture_profile=recommendation,
            registry_version=registry_version,
            dependency_graph_revision=graph.revision.value,
            valid=False,
        )

    def _operation_lock(self, dry_run: bool) -> AbstractContextManager[object]:
        return (
            _NullContext() if dry_run else self._filesystem.lock(_DECOMPOSITION_LOCK, timeout=5.0)
        )


def _load_recommendation_catalog() -> AssetDecompositionRecommendationCatalogContract:
    try:
        payload = (
            resources.files("ludowright.decomposition_data")
            .joinpath(_RECOMMENDATIONS_RESOURCE)
            .read_bytes()
        )
        return AssetDecompositionRecommendationCatalogContract.model_validate(json.loads(payload))
    except (OSError, TypeError, json.JSONDecodeError, ValidationError) as error:
        raise AssetDecompositionError(
            "packaged decomposition recommendations are invalid"
        ) from error


def _canonical_asset_id(asset_id: str) -> str:
    try:
        return AssetId(asset_id).value
    except (DomainValidationError, TypeError) as error:
        raise AssetDecompositionError(str(error)) from error


def _replace_decomposition(
    current: AssetContract,
    request: AssetDecompositionContract,
) -> AssetContract:
    payload = current.model_dump(mode="json")
    payload["components"] = [item.model_dump(mode="json") for item in request.components]
    payload["variants"] = [item.model_dump(mode="json") for item in request.variants]
    payload["states"] = [item.model_dump(mode="json") for item in request.states]
    return AssetContract.model_validate(payload)


def _decomposition_from_asset(
    asset: AssetContract,
    graph: DependencyGraph,
) -> AssetDecompositionContract:
    key = DependencyKey(DependencyNodeKind.ASSET, asset.id)
    dependencies: tuple[AssetDependencyContract, ...] = ()
    if any(node.key == key for node in graph.nodes):
        dependencies = tuple(
            AssetDependencyContract(
                depends_on=edge.source.id,
                invalidation_mode=edge.invalidation_mode,
            )
            for edge in graph.dependencies_of(key)
            if edge.source.kind is DependencyNodeKind.ASSET
            and edge.relation is DependencyRelation.REQUIRES
        )
    return AssetDecompositionContract(
        asset_id=asset.id,
        components=tuple(asset.components),
        variants=tuple(asset.variants),
        states=tuple(asset.states),
        dependencies=tuple(sorted(dependencies, key=lambda item: item.depends_on)),
    )


def _dependency_corrections(
    asset_id: str,
    dependencies: Iterable[AssetDependencyContract],
    assets: tuple[AssetContract, ...],
) -> tuple[AssetDecompositionCorrectionContract, ...]:
    known_ids = {asset.id for asset in assets}
    corrections: list[AssetDecompositionCorrectionContract] = []
    for dependency in dependencies:
        if dependency.depends_on not in known_ids:
            corrections.append(
                _correction(
                    code="unknown-dependency",
                    severity="error",
                    subject=dependency.depends_on,
                    message="the prerequisite asset is not present in the registry",
                    suggestion="create or discover the prerequisite asset before linking it",
                )
            )
        if dependency.depends_on == asset_id:
            corrections.append(
                _correction(
                    code="self-dependency",
                    severity="error",
                    subject=asset_id,
                    message="an asset cannot depend on itself",
                    suggestion="choose another prerequisite asset or remove the dependency",
                )
            )
    return tuple(corrections)


def _find_recommendation(
    catalog: AssetDecompositionRecommendationCatalogContract,
    family: AssetFamily,
    subtype: str | None,
) -> AssetDecompositionRecommendationRuleContract | None:
    exact = next(
        (
            rule
            for rule in catalog.rules
            if rule.family is family and rule.subtype == subtype and subtype is not None
        ),
        None,
    )
    if exact is not None:
        return exact
    return next(
        (rule for rule in catalog.rules if rule.family is family and rule.subtype is None),
        None,
    )


def _plan_graph(
    graph: DependencyGraph,
    *,
    asset_id: str,
    asset_changed: bool,
    dependencies: tuple[AssetDependencyContract, ...],
) -> DependencyGraph:
    current = graph
    asset_key = DependencyKey(DependencyNodeKind.ASSET, asset_id)
    desired = {
        DependencyKey(DependencyNodeKind.ASSET, dependency.depends_on): dependency.invalidation_mode
        for dependency in dependencies
    }
    existing_asset_edges = tuple(
        edge
        for edge in current.edges
        if edge.target == asset_key and edge.source.kind is DependencyNodeKind.ASSET
    )
    for edge in existing_asset_edges:
        if edge.relation is not DependencyRelation.REQUIRES:
            raise ValueError(
                f"asset dependency edge uses an incompatible relation: {edge.source.token}"
            )
        if edge.source not in desired:
            if _edge_in_invalidation_path(current, edge.source, edge.target):
                raise ValueError(
                    f"cannot remove dependency edge with persisted impact history: "
                    f"{edge.source.token} -> {edge.target.token}"
                )
            current = current.disconnect(edge.source, edge.target, edge.relation)
        elif edge.invalidation_mode is not desired[edge.source]:
            if _edge_in_invalidation_path(current, edge.source, edge.target):
                raise ValueError(
                    f"cannot change dependency policy with persisted impact history: "
                    f"{edge.source.token} -> {edge.target.token}"
                )
            current = current.disconnect(edge.source, edge.target, edge.relation)

    for source in sorted(desired):
        if not any(node.key == source for node in current.nodes):
            current = current.add_node(
                DependencyNode(
                    key=source,
                    revision=RevisionVersion(1),
                    freshness=FreshnessState.FRESH,
                )
            )
    if not any(node.key == asset_key for node in current.nodes):
        current = current.add_node(
            DependencyNode(
                key=asset_key,
                revision=RevisionVersion(1),
                freshness=FreshnessState.FRESH,
            )
        )
    elif asset_changed:
        node = current.get_node(asset_key)
        next_revision = RevisionVersion(node.revision.value + 1)
        if any(
            edge.invalidation_mode is not InvalidationMode.NONE
            for edge in current.dependencies_of(asset_key)
        ):
            current = current.refresh(asset_key, next_revision).graph
        else:
            current = current.publish_revision(asset_key, next_revision).graph

    for source, mode in sorted(desired.items()):
        if not any(edge.source == source and edge.target == asset_key for edge in current.edges):
            current = current.connect(
                source,
                asset_key,
                DependencyRelation.REQUIRES,
                mode,
            )
    return current


def _edge_in_invalidation_path(
    graph: DependencyGraph,
    source: DependencyKey,
    target: DependencyKey,
) -> bool:
    return any(
        any(
            left == source and right == target
            for left, right in zip(cause.path, cause.path[1:], strict=False)
        )
        for node in graph.nodes
        for cause in node.invalidations
    )


def _event_payload(
    request: AssetDecompositionContract,
    recommendation: CaptureProfileRecommendationContract,
    graph: DependencyGraph,
) -> dict[str, FrozenJsonValue]:
    return {
        "component_ids": tuple(item.id for item in request.components),
        "variant_ids": tuple(item.id for item in request.variants),
        "state_ids": tuple(item.id for item in request.states),
        "dependency_ids": tuple(item.depends_on for item in request.dependencies),
        "dependency_graph_revision": graph.revision.value,
        "capture_profile_id": recommendation.profile_id,
        "capture_profile_version": recommendation.profile_version,
    }


def _report(
    *,
    state: DecompositionState,
    dry_run: bool,
    asset: AssetContract,
    decomposition: AssetDecompositionContract,
    corrections: tuple[AssetDecompositionCorrectionContract, ...],
    capture_profile: CaptureProfileRecommendationContract,
    registry_version: int,
    dependency_graph_revision: int,
    valid: bool,
) -> AssetDecompositionReportContract:
    return AssetDecompositionReportContract(
        state=state,
        dry_run=dry_run,
        asset_id=asset.id,
        asset=asset,
        decomposition=decomposition,
        corrections=tuple(
            sorted(corrections, key=lambda item: (item.severity, item.code, item.subject))
        ),
        capture_profile=capture_profile,
        registry_path=DEFAULT_ASSET_REGISTRY_PATH.value,
        registry_version=registry_version,
        dependency_graph_path=DEFAULT_DEPENDENCY_GRAPH_PATH.value,
        dependency_graph_revision=dependency_graph_revision,
        valid=valid,
    )


def _correction(
    *,
    code: CorrectionCode,
    severity: CorrectionSeverity,
    subject: str,
    message: str,
    suggestion: str,
) -> AssetDecompositionCorrectionContract:
    return AssetDecompositionCorrectionContract(
        code=code,
        severity=severity,
        subject=subject,
        message=message[:4_000],
        suggestion=suggestion[:4_000],
    )


def _read_optional_bytes(filesystem: ProjectFilesystem, path: RepositoryPath) -> bytes | None:
    try:
        return filesystem.read_bytes(path)
    except FileNotFoundError:
        return None


def _restore_graph(
    filesystem: ProjectFilesystem,
    prior_bytes: bytes | None,
    expected_current: bytes | None,
) -> None:
    current = _read_optional_bytes(filesystem, DEFAULT_DEPENDENCY_GRAPH_PATH)
    if current != expected_current:
        raise AssetDecompositionRollbackError(
            "cannot safely roll back the dependency graph after another writer changed it"
        )
    if prior_bytes is None:
        filesystem.remove_file(DEFAULT_DEPENDENCY_GRAPH_PATH)
    else:
        filesystem.write_bytes(DEFAULT_DEPENDENCY_GRAPH_PATH, prior_bytes)


class _NullContext:
    def __enter__(self) -> _NullContext:
        return self

    def __exit__(self, *_args: object) -> None:
        return None
