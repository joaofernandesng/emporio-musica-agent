# Raw data files

`data/raw/` holds the files exactly as delivered by the store. Their content is
immutable: nothing in this project edits them. Corrections are always expressed
as derived columns or flags downstream (see `docs/data_quality.md`).

The original file names contain spaces and accents. They are not renamed;
the loader maps logical table names to the real file names
(`src/emporio/build_db.py`, `RAW_FILES`).

| Logical name | File in `data/raw/` | sha256 |
|---|---|---|
| categories | `desafio_tecnico_ai_eng - categories.csv` | `7a7901e16c8c6357a956031ada45a6fd6a4cc9bd7bc1edc05448cc55b01b0a9e` |
| customers | `desafio_tecnico_ai_eng - customers.csv` | `1cd724dc86eac6258913cc890abf23d3893c57a99c9325ebfb91dfad3c7b0f37` |
| order_items | `desafio_tecnico_ai_eng - order_items.csv` | `7656eb681821d48e0c932f61d3188309b955c25446578235f2d8e69604b0f0bc` |
| orders | `desafio_tecnico_ai_eng - orders.csv` | `deb9c2480605d8d22117d569f0045fd156c5e9a58ffeebb847ff61b3b9512fd5` |
| products | `desafio_tecnico_ai_eng - products.csv` | `78d911d96ee891abb163b6c858e895025aa530ab27d0290540f05d5098377c12` |
| promotions | `desafio_tecnico_ai_eng - promotions.csv` | `cbe08c7e91b00437c0c00a7ef1486deba73de52d23e3f97f51a7dbd557d759e0` |
| policies manual (PDF) | `políticas_da_loja.pdf` | `b7527f96896929f4ba929de117651c6717e25b7a3b92b34bc54d5ba32f6156f7` |
