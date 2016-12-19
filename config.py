# -*- coding: utf-8 -*-
"""
Configuration Settings
----------------------
Built for the VIRUS instrument as well as LRS2 on HET

@author: gregz
"""

# Bottom Amplifier for each side ---
Amps = ["LL", "RU"]

# Connecting the bottom ampliefer with the top and total side
Amp_dict = {"LL": ["LU","L"], "RU": ["RL","R"]}

# Wavelength limits for each side as defined by the bottom amplifier id
virus_wl = {"LL": [3490,5500], "RU": [3490,5500]}
lrs2b_wl = {"LL": [3633,4655], "RU": [4550,7000]}
lrs2r_wl = {"LL": [3490,5500], "RU": [3490,5500]}

# Name prefix for the normalized spectrum used for the wavelength solution
virus_sn = {"LL": "virus", "RU": "virus"}
lrs2b_sn = {"LL": "lrs2_uv", "RU": "lrs2_orange"}
lrs2r_sn = {"LL": "lrs2_red", "RU": "lrs2_farred"}

# Name of the IFUcen file for fiber positions
virus_fn = {"LL": "IFUcen_HETDEX.txt", "RU": "IFUcen_HETDEX.txt"}
lrs2b_fn = {"LL": "LRS2_B_UV_mapping.txt", "RU": "LRS2_B_OR_mapping.txt"}
lrs2r_fn = {"LL": "LRS2_R_RED_mapping.txt", "RU": "LRS2_R_FAR_mapping.txt"}

# Pixel width in radius over which the fibermodel is defined
virus_fs = 8.
lrs2b_fs = 6.
lrs2r_fs = 6.

# Dispersion scale for making the Fe/CuFe files
virus_di = {"LL": 1.9, "RU": 1.9}
lrs2b_di = {"LL": 0.5, "RU": 1.2}
lrs2r_di = {"LL": 1.2, "RU": 1.2}