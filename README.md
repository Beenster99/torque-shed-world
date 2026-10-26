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

- `profile/cROW_COLUMN.json`: each cell's **place profile** (country and region, Köppen-Geiger zone, the months'
  temperature, rain and sunshine, cover mix, altitude, coast, how built up it is), its hash in the index's `"profiles"`.
  Made by the game's `tools/profile_bake.py` (see `docs/place_profile.md` there); `.github/workflows/profiles.yml`
  (**Profile the cells**) makes them after every bake, only for cells whose inputs changed.

- `worker/`: the **survey** worker (Cloudflare, free plan) the game asks to bake cells nobody has baked yet, when a
  crew presses Survey on the Route planner TV. See `worker/README.md` for setting it up.

Nothing here runs or costs anything between bakes: Actions are free for a public repository, and release assets are
served by GitHub.

## Credits and licence

The road, building, place and land data are from [Overture Maps](https://overturemaps.org) (© OpenStreetMap
contributors, Overture Maps Foundation), published under the ODbL; each cell's `region.json` lists its sources.

The profiles are made from Natural Earth (public domain); Beck, H.E. et al. (2023) Köppen-Geiger maps (CC BY 4.0); ESA
WorldCover 2021 (© ESA WorldCover project 2021 / Contains modified Copernicus Sentinel data (2021) processed by ESA
WorldCover consortium, CC BY 4.0); CRU TS 4.09 (Climatic Research Unit, University of East Anglia, and Met Office: Open
Government Licence); and the terrain tiles the cells use.
