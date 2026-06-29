# Bundled font licences

`charr-datagen` bundles the font files in this directory so chart rendering is reproducible across machines
(docs/adr/0021). The fonts are redistributable under the SIL Open Font License 1.1 (`OFL-1.1.txt`) or the Apache License
2.0 (`Apache-2.0.txt`). The fonts are licensed under those terms; the `charr-datagen` source code is under the project's
own licence. Each bundled font, its source, and its licence:

| Font           | File                        | Licence    | Copyright                                                                                         |
| -------------- | --------------------------- | ---------- | ------------------------------------------------------------------------------------------------- |
| Open Sans      | `OpenSans-Regular.ttf`      | OFL-1.1    | Copyright 2020 The Open Sans Project Authors (https://github.com/googlefonts/opensans)            |
| Montserrat     | `Montserrat-Regular.ttf`    | OFL-1.1    | Copyright 2011 The Montserrat Project Authors (https://github.com/JulietaUla/Montserrat)          |
| Lora           | `Lora-Regular.ttf`          | OFL-1.1    | Copyright 2011 The Lora Project Authors (https://github.com/cyrealtype/Lora-Cyrillic), RFN "Lora" |
| Roboto Slab    | `RobotoSlab-Regular.ttf`    | Apache-2.0 | Copyright 2018 The Roboto Slab Project Authors (https://github.com/googlefonts/robotoslab)        |
| JetBrains Mono | `JetBrainsMono-Regular.ttf` | OFL-1.1    | Copyright 2020 The JetBrains Mono Project Authors (https://github.com/JetBrains/JetBrainsMono)    |
| Caveat         | `Caveat-Regular.ttf`        | OFL-1.1    | Copyright 2014 The Caveat Project Authors (https://github.com/googlefonts/caveat)                 |

OFL reserved font names (where declared) are not reused: the bundled files are the upstream releases, unmodified.
