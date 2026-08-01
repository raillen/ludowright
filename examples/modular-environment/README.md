# Modular environment example

`Mossbridge Commons` is a deterministic modular-environment example. It
combines a building, a reusable module kit, a road, a tree, and a plant while
keeping component, state, socket, and connection guidance in the existing
versioned profiles.

Initialize a project with the published initializer and copy the example
inputs:

```bash
ludowright init ./mossbridge-commons --name "Mossbridge Commons" \
  --template minimal --non-interactive
cp -R examples/modular-environment/project/. ./mossbridge-commons/
```

Register the assets:

```bash
ludowright assets create ./mossbridge-commons --input imports/commons-building.json
ludowright assets create ./mossbridge-commons --input imports/courtyard-kit.json
ludowright assets create ./mossbridge-commons --input imports/old-road.json
ludowright assets create ./mossbridge-commons --input imports/oak-tree.json
ludowright assets create ./mossbridge-commons --input imports/field-plant.json
```

The building and modular kit reuse the hard-surface catalog. The tree and
plant reuse the visual-specialty catalog. The road is the smallest explicit
generic capture profile needed to connect the terrain/road taxonomy to the
same planner; it is data in the example and is not a new package profile.

All references are candidates, so the planner derives the complete workload
but remains blocked until each exact reference revision is approved. The
connection matrix is descriptive profile guidance: it demonstrates module
edges and a root-to-connector socket without mutating the project dependency
graph.

SQLite, event log, dependency graph, normalized images, receipts, sheets, and
package archives are derived outputs and are intentionally not committed.
