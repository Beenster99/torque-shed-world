# Torque Shed world

The world's roads for [Torque Shed](https://github.com/Beenster99/torque-shed)'s adventures, baked in **cells**: 0.25°
squares of the world's grid, each holding the roads (as a graph), buildings, towns and villages, places to stop,
landmarks and land cover there. The game fetches the cells a journey crosses, checks each against its hash, and
stitches them together; the land's heights come from [Mapterhorn](https://mapterhorn.com)'s map tiles. See
`docs/ride_anywhere_plan.md` in the game's repository for the design.

## What's here

- `index.json`: the Overture Maps release the cells are baked from, and each baked cell by `ROW_COLUMN` (rows north from
  the south pole, columns east from 180° W): its hash, size and download URL, or `"empty": true` where there are no roads.
- The cells themselves are release assets, `cROW_COLUMN-HASH.zip`, one release per 5° block (`cells-RELEASE-bR_C`).
- `.github/workflows/bake.yml`: bakes cells on request (Actions tab, **Bake cells**, **Run workflow**) with the game's
  own `tools/region_bake.py --cell`, 20 at a time, and adds them to the index. Give it points (`LAT,LON`) or boxes
  (`SOUTH,WEST,NORTH,EAST`); cells the index already has are skipped. A run bakes up to 250 cells.

Nothing here runs or costs anything between bakes: Actions are free for a public repository, and release assets are
served by GitHub.

## Credits and licence

The road, building, place and land data are from [Overture Maps](https://overturemaps.org) (© OpenStreetMap
contributors, Overture Maps Foundation), published under the ODbL; each cell's `region.json` lists its sources.
