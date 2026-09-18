# -*- coding: utf-8 -*-
"""Build the RES_V1 draft accuracy set (2026-09-17).

One item per release, in set order. `rows` is the list of resource rows the release states, one
per deposit per category, per the label guide. `complete: false` marks an item whose row list is
known to be partial -- a release with more tables than could be read back in one look -- so that
precision still counts it and recall does not.
"""
import hashlib
import json

def R(dep, cat, t=None, g=None, c=None, cut=None, ctx="announced", basis="resource"):
    return {"deposit": dep, "category": cat, "tonnes": t, "grades": g or [], "contained": c or [],
            "cut_off": cut, "context": ctx, "basis": basis}

S = []
def add(eid, tic, date, rows, mre=None, conf="high", complete=True, note=None, excluded=False):
    S.append({"event_id": eid, "ticker": tic, "published_at": date, "estimate": bool(rows),
              "mre_type": mre, "rows": rows, "confidence": conf, "complete": complete,
              "note": note, "excluded": excluded})

def none(eid, tic, date, note):
    add(eid, tic, date, [], None, "high", True, note)

# ---- releases that state no figures --------------------------------------------------------
none("2798ef7c3318", "FNI.CN", "2026-09-16", "new zones of mineralization; refers back to a maiden MRE announced six days earlier but states no figures")
none("35c4d0362a8c", "EDDY.V", "2026-09-03", "technical report filing, no figures")
none("0f3b93ce01f0", "SRL.V", "2026-08-13", "technical report filing, no figures")
none("7cb7a195317b", "WDO.TO", "2026-08-06", "technical report filing; reserve plans discussed, no figures stated")
none("f202eff910c4", "MGG.V", "2026-07-14", "engages a consultant to prepare an update -- an intention, not an estimate")
none("d88373373de6", "SAGA.V", "2026-06-29", "second drill rig, nearing completion of MRE drilling")
none("cb713629c400", "NAU.V", "2026-04-09", "drill intercepts; a maiden MRE is the stated goal")
none("4df5bee0e841", "AVE.CN", "2026-04-01", "357-char body about the Corvo uranium drill programme under a Sting copper headline -- the body does not match the headline")
none("96978d2c3c02", "NEXX.CN", "2026-02-13", "technical report filing, no figures")
none("ad13dbca72dd", "MGG.V", "2025-11-27", "phase 2 expansion drill programme")
none("766077674c2b", "AVE.CN", "2025-10-27", "the same 357-char Corvo body as the April release")
none("07941625ccc7", "PEX.V", "2025-09-18", "technical report filing, no figures")
none("4e5e39a1cf2f", "AMC.TO", "2025-08-14", "files the report supporting a resource announced in June; no figures in this release")
none("6ed1b8009461", "OMI.V", "2025-07-14", "moving into resource-estimate drilling")
none("ff07f535504b", "SCOT.V", "2025-06-23", "technical report filing, no figures")
none("252c12d62a62", "DEC.V", "2025-04-21", "buys ground surrounded by other companies' deposits; the 201.67 Moz is not Decade's")
none("044036f2ce55", "CAP.CN", "2025-03-24", "announces a substantial updated MRE, but the stored body ends at 'Mineral Resource Statement Notes:' -- the table did not survive ingestion")
none("2fd8b4afb297", "SGLD.V", "2025-01-24", "shareholder summary; the maiden resource is described as imminent")
none("ebdd9de72e62", "GRBM.CN", "2024-10-03", "technical report filing, no figures")
none("2c48e358e4dc", "GOH.CN", "2024-05-07", "technical report filing, no figures")
none("9221d62cc64d", "PURR.CN", "2023-11-16", "technical report filing, no figures")
none("fac405a170d9", "KUYA.CN", "2021-12-03", "voluntary technical report filing, no figures")
none("5ac7a701e533", "NICO.CN", "2021-03-22", "about to start drilling to expand resources")
none("ff287f532430", "NRDX.CN", "2019-02-18", "technical report filing, no figures")
none("34ac1515261e", "PGOL.CN", "2010-01-27", "862-char filing announcement, no figures")

# ---- releases with figures ------------------------------------------------------------------
add("6d275868ff32", "NEO.TO", "2026-08-24", [
    R("Sarfartoq ST1", "Indicated", 7475000, [{"metal": "TREO", "value": 1.56, "unit": "%"}]),
    R("Sarfartoq ST1", "Inferred", 2603000, [{"metal": "TREO", "value": 1.36, "unit": "%"}]),
    R("Sarfartoq ST1", "Total", 10078000, [{"metal": "TREO", "value": 1.51, "unit": "%"}]),
], "Update", "low", False,
    "three scenario tables (open pit, underground, hybrid); only one was read back, so the scenario on these rows is unconfirmed. Filed under NEO.TO but the company in the body is Nasdaq: GRML -- wrong-ticker attribution")

add("4861c6b72672", "NVRO.V", "2026-07-23", [
    R("NVRO Metals Hub oxide", "Proven", 930000, basis="reserve"),
], "Maiden", "low", False, "maiden oxide mineral RESERVE; the resource is given only as percentages of the reserve")

add("021b35a26ef6", "WRLG.V", "2026-06-09", [
    R("Rowan", "Indicated", 754514, [{"metal": "Au", "value": 13.03, "unit": "g/t"}], [{"metal": "Au", "value": 334825, "unit": "oz"}], "2.00 g/t Au"),
    R("Rowan", "Inferred", 360323, [{"metal": "Au", "value": 15.31, "unit": "g/t"}], [{"metal": "Au", "value": 179013, "unit": "oz"}], "2.00 g/t Au"),
    R("Mt. Jamie", "Indicated", 108775, [{"metal": "Au", "value": 14.13, "unit": "g/t"}], [{"metal": "Au", "value": 49407, "unit": "oz"}], "3.80 g/t Au"),
    R("Mt. Jamie", "Inferred", 92972, [{"metal": "Au", "value": 11.97, "unit": "g/t"}], [{"metal": "Au", "value": 35791, "unit": "oz"}], "3.80 g/t Au"),
], "Update")

add("df89494dd36e", "MILI.CN", "2026-05-22", [
    R(u"Trojárová", "Inferred", 6500000,
      [{"metal": "Sb", "value": 1.02, "unit": "%"}, {"metal": "Au", "value": 1.06, "unit": "g/t"}],
      [{"metal": "Sb", "value": 67, "unit": "kt"}, {"metal": "Au", "value": 222, "unit": "koz"}],
      "0.8% SbEq"),
], "Maiden")

add("7c60dd506e12", "GGA.V", "2026-05-11", [
    R("San Francisco Mine OP", "Measured", 41024000, [{"metal": "Au", "value": 0.38, "unit": "g/t"}], [{"metal": "Au", "value": 498900, "unit": "oz"}], "0.09 g/t Au"),
    R("San Francisco Mine OP", "Indicated", 38299000, [{"metal": "Au", "value": 0.37, "unit": "g/t"}], [{"metal": "Au", "value": 456800, "unit": "oz"}], "0.09 g/t Au"),
    R("San Francisco Mine OP", "Measured & Indicated", 79323000, [{"metal": "Au", "value": 0.37, "unit": "g/t"}], [{"metal": "Au", "value": 955700, "unit": "oz"}], "0.09 g/t Au"),
    R("San Francisco Mine OP", "Inferred", 7464000, [{"metal": "Au", "value": 0.39, "unit": "g/t"}], [{"metal": "Au", "value": 93300, "unit": "oz"}], "0.09 g/t Au"),
    R("La Chicharra Mine OP", "Measured", 7241000, [{"metal": "Au", "value": 0.36, "unit": "g/t"}], [{"metal": "Au", "value": 82800, "unit": "oz"}], "0.07 g/t Au"),
    R("La Chicharra Mine OP", "Indicated", 13892000, [{"metal": "Au", "value": 0.32, "unit": "g/t"}], [{"metal": "Au", "value": 143800, "unit": "oz"}], "0.07 g/t Au"),
    R("La Chicharra Mine OP", "Measured & Indicated", 21132000, [{"metal": "Au", "value": 0.33, "unit": "g/t"}], [{"metal": "Au", "value": 226600, "unit": "oz"}], "0.07 g/t Au"),
    R("La Chicharra Mine OP", "Inferred", 1040000, [{"metal": "Au", "value": 0.37, "unit": "g/t"}], [{"metal": "Au", "value": 12400, "unit": "oz"}], "0.07 g/t Au"),
    R("North Pit Mine OP", "Indicated", 4630000, [{"metal": "Au", "value": 0.30, "unit": "g/t"}], [{"metal": "Au", "value": 44300, "unit": "oz"}], "0.08 g/t Au"),
    R("North Pit Mine OP", "Measured & Indicated", 4630000, [{"metal": "Au", "value": 0.30, "unit": "g/t"}], [{"metal": "Au", "value": 44300, "unit": "oz"}], "0.08 g/t Au"),
    R("North Pit Mine OP", "Inferred", 8764000, [{"metal": "Au", "value": 0.26, "unit": "g/t"}], [{"metal": "Au", "value": 72700, "unit": "oz"}], "0.08 g/t Au"),
    R("Total Resources", "Measured", 48265000, [{"metal": "Au", "value": 0.37, "unit": "g/t"}], [{"metal": "Au", "value": 581700, "unit": "oz"}]),
    R("Total Resources", "Indicated", 56821000, [{"metal": "Au", "value": 0.35, "unit": "g/t"}], [{"metal": "Au", "value": 644900, "unit": "oz"}]),
    R("Total Resources", "Measured & Indicated", 105086000),
], "Update", "high", False,
    "North Pit's Measured line carries no figures and is not a row. The Total Resources block was cut off after M&I tonnes")

add("a203279b1bba", "FF.TO", "2026-04-29", [
    R("Ming Mine", "Measured", 6300000, [{"metal": "CuEq", "value": 1.9, "unit": "%"}], ctx="background"),
    R("Ming Mine", "Indicated", 41200000, [{"metal": "CuEq", "value": 3.2, "unit": "%"}], ctx="background"),
    R("Ming Mine", "Measured & Indicated", 47500000, [{"metal": "CuEq", "value": 3.1, "unit": "%"}], ctx="background"),
    R("Ming Mine", "Inferred", 23100000, [{"metal": "CuEq", "value": 5.9, "unit": "%"}], ctx="background"),
], None, "low", False,
    "drill-results release; the eleven tables restate the existing resource ahead of an update, so every row is background. Reported under JORC as well as NI 43-101")

add("e942aa6cf45a", "RUA.TO", "2026-03-03", [
    R("Auld Creek - Bonanza", "Indicated", 40000, [{"metal": "Au", "value": 2.26, "unit": "g/t"}, {"metal": "Sb", "value": 1.6, "unit": "%"}], [{"metal": "Au", "value": 3, "unit": "koz"}, {"metal": "Sb", "value": 1, "unit": "kt"}]),
    R("Auld Creek - Bonanza", "Inferred", 180000, [{"metal": "Au", "value": 1.8, "unit": "g/t"}, {"metal": "Sb", "value": 0.8, "unit": "%"}], [{"metal": "Au", "value": 11, "unit": "koz"}, {"metal": "Sb", "value": 1, "unit": "kt"}]),
    R("Auld Creek - Fraternal", "Indicated", 260000, [{"metal": "Au", "value": 3.3, "unit": "g/t"}, {"metal": "Sb", "value": 1.1, "unit": "%"}], [{"metal": "Au", "value": 28, "unit": "koz"}, {"metal": "Sb", "value": 3, "unit": "kt"}]),
    R("Auld Creek - Fraternal", "Inferred", 1070000, [{"metal": "Au", "value": 2.0, "unit": "g/t"}, {"metal": "Sb", "value": 0.8, "unit": "%"}], [{"metal": "Au", "value": 69, "unit": "koz"}, {"metal": "Sb", "value": 9, "unit": "kt"}]),
    R("Auld Creek", "Total", 300000, [{"metal": "Au", "value": 3.18, "unit": "g/t"}], [{"metal": "Au", "value": 31, "unit": "koz"}]),
], "Update", "low", False,
    "four MRE prospects across Reefton and Glamorgan; only the Auld Creek table was read back. The Total line is Auld Creek's total for the Indicated category, not a category of its own")

add("29000dbb8fd6", "EXN.V", "2026-02-23", [
    R("Mallay Mine", "Indicated", 890000,
      [{"metal": "Ag", "value": 195, "unit": "g/t"}, {"metal": "Pb", "value": 3.33, "unit": "%"}, {"metal": "Zn", "value": 4.83, "unit": "%"}],
      [{"metal": "Ag", "value": 5.57, "unit": "Moz"}, {"metal": "Pb", "value": 65, "unit": "Mlb"}, {"metal": "Zn", "value": 95, "unit": "Mlb"}]),
    R("Mallay Mine", "Inferred", 362000,
      [{"metal": "Ag", "value": 149, "unit": "g/t"}, {"metal": "Pb", "value": 2.67, "unit": "%"}, {"metal": "Zn", "value": 4.32, "unit": "%"}],
      [{"metal": "Ag", "value": 1.74, "unit": "Moz"}, {"metal": "Pb", "value": 21, "unit": "Mlb"}, {"metal": "Zn", "value": 34, "unit": "Mlb"}]),
], "Update", "high", False,
    "the announced figures are in the prose; the table behind them is a cut-off sensitivity at 50/100/250 g/t AgEq whose rows were not all read back")

add("4cb7227ec825", "KDK.V", "2026-01-23", [
    R("MPD - Gate", "Indicated", 56400000, [{"metal": "CuEq", "value": 0.42, "unit": "%"}, {"metal": "Cu", "value": 0.31, "unit": "%"}, {"metal": "Au", "value": 0.14, "unit": "g/t"}, {"metal": "Ag", "value": 1.18, "unit": "g/t"}], [{"metal": "Cu", "value": 385, "unit": "Mlb"}, {"metal": "Au", "value": 0.25, "unit": "Moz"}, {"metal": "CuEq", "value": 522, "unit": "Mlb"}]),
    R("MPD - West", "Indicated", 14200000, [{"metal": "CuEq", "value": 0.37, "unit": "%"}, {"metal": "Cu", "value": 0.21, "unit": "%"}, {"metal": "Au", "value": 0.24, "unit": "g/t"}, {"metal": "Ag", "value": 0.80, "unit": "g/t"}], [{"metal": "Cu", "value": 66, "unit": "Mlb"}, {"metal": "Au", "value": 0.11, "unit": "Moz"}, {"metal": "CuEq", "value": 116, "unit": "Mlb"}]),
    R("MPD - South", "Indicated", 12300000, [{"metal": "CuEq", "value": 0.30, "unit": "%"}, {"metal": "Cu", "value": 0.25, "unit": "%"}, {"metal": "Au", "value": 0.07, "unit": "g/t"}, {"metal": "Ag", "value": 1.17, "unit": "g/t"}]),
    R("MPD", "Total", 82900000, [{"metal": "CuEq", "value": 0.39, "unit": "%"}], [{"metal": "Cu", "value": 519, "unit": "Mlb"}, {"metal": "Au", "value": 0.39, "unit": "Moz"}]),
], "Maiden", "high", False,
    "seven zones; Gate, West and South read back plus the prose totals. Each table row carries its own effective date")

add("e7038798e036", "ADY.V", "2026-01-13", [
    R("Wapolu", "Indicated", None, [{"metal": "Au", "value": 1.00, "unit": "g/t"}], [{"metal": "Au", "value": 33, "unit": "koz"}]),
    R("Wapolu", "Inferred", 12700000, [{"metal": "Au", "value": 0.97, "unit": "g/t"}], [{"metal": "Au", "value": 393, "unit": "koz"}]),
    R("PNG portfolio", "Indicated", None, None, [{"metal": "Au", "value": 206000, "unit": "oz"}], ctx="background"),
    R("PNG portfolio", "Inferred", None, None, [{"metal": "Au", "value": 2193000, "unit": "oz"}], ctx="background"),
    R("Feni Island", "Inferred", 60400000, [{"metal": "Au", "value": 0.75, "unit": "g/t"}], ctx="background"),
], "Update", "high", True,
    "Wapolu is the announcement; the portfolio totals and the 2021 Feni Island resource are background")

add("964e4463714a", "KLD.V", "2025-12-16", [
    R("Regnault", "Inferred", 14500000,
      [{"metal": "Au", "value": 5.47, "unit": "g/t"}, {"metal": "Ag", "value": 5.18, "unit": "g/t"}],
      [{"metal": "Au", "value": 2.55, "unit": "Moz"}, {"metal": "Ag", "value": 2.41, "unit": "Moz"}]),
], "Maiden", "high", True, "Kenorland holds a 4% NSR royalty on the deposit; the estimate is still the announcement")

add("7ebb58dd445d", "PMET.TO", "2025-11-14", [
    R("Shaakichiuwaanaan CV5", "Indicated", 108000000, [{"metal": "Li2O", "value": 1.40, "unit": "%"}, {"metal": "Cs2O", "value": 0.11, "unit": "%"}, {"metal": "Ta2O5", "value": 166, "unit": "ppm"}, {"metal": "Ga", "value": 66, "unit": "ppm"}], ctx="background"),
    R("Shaakichiuwaanaan CV5", "Inferred", 33400000, [{"metal": "Li2O", "value": 1.33, "unit": "%"}, {"metal": "Ta2O5", "value": 155, "unit": "ppm"}, {"metal": "Ga", "value": 65, "unit": "ppm"}], ctx="background"),
    R("Shaakichiuwaanaan CV13/Vega", "Indicated", 690000, [{"metal": "Cs2O", "value": 4.40, "unit": "%"}], ctx="background"),
    R("Shaakichiuwaanaan CV13/Vega", "Inferred", 1700000, [{"metal": "Cs2O", "value": 2.40, "unit": "%"}], ctx="background"),
], "Restated", "low", False, "feasibility-study filing; the resource is restated, not announced")

add("6d15cdcd5940", "ILI.V", "2025-10-15", [
    R("Jackpot", "Indicated", 3100000, [{"metal": "Li2O", "value": 0.85, "unit": "%"}]),
    R("Jackpot", "Inferred", 5300000, [{"metal": "Li2O", "value": 0.91, "unit": "%"}]),
], "Maiden")

add("dd1ce102c442", "CRUZ.CN", "2026-03-18", [
    R("Solar Lithium", "Indicated", 35000000, [{"metal": "Li", "value": 697, "unit": "ppm"}], [{"metal": "LCE", "value": 128000, "unit": "t"}], "500 ppm Li"),
    R("Solar Lithium", "Inferred", 103000000, [{"metal": "Li", "value": 641, "unit": "ppm"}], [{"metal": "LCE", "value": 352000, "unit": "t"}], "500 ppm Li"),
    R("Solar Lithium", "Indicated", 50000000, [{"metal": "Li", "value": 608, "unit": "ppm"}], [{"metal": "LCE", "value": 161000, "unit": "t"}], "300 ppm Li", "alternative cut-off"),
], "Maiden", "high", True, "the 500 ppm case is Stantec's stated base case; the 300 ppm case is the same estimate at a lower cut-off")

add("96e0b5b2d7f3", "XXIX.V", "2025-06-03", [
    R("Opemiska pit-constrained", "Indicated", 62706000, [{"metal": "CuEq", "value": 1.04, "unit": "%"}, {"metal": "Cu", "value": 0.76, "unit": "%"}, {"metal": "Ag", "value": 1.71, "unit": "g/t"}, {"metal": "Au", "value": 0.31, "unit": "g/t"}], [{"metal": "Cu", "value": 1047, "unit": "Mlb"}, {"metal": "Ag", "value": 3450, "unit": "koz"}, {"metal": "Au", "value": 634, "unit": "koz"}], "0.15% CuEq"),
    R("Opemiska pit-constrained", "Inferred", 78485000, [{"metal": "CuEq", "value": 0.41, "unit": "%"}, {"metal": "Cu", "value": 0.26, "unit": "%"}, {"metal": "Ag", "value": 0.61, "unit": "g/t"}, {"metal": "Au", "value": 0.17, "unit": "g/t"}], [{"metal": "Cu", "value": 457, "unit": "Mlb"}, {"metal": "Ag", "value": 1530, "unit": "koz"}, {"metal": "Au", "value": 419, "unit": "koz"}], "0.15% CuEq"),
    R("Opemiska out-of-pit", "Indicated", 6947000, [{"metal": "CuEq", "value": 1.85, "unit": "%"}, {"metal": "Cu", "value": 1.59, "unit": "%"}, {"metal": "Ag", "value": 2.76, "unit": "g/t"}, {"metal": "Au", "value": 0.28, "unit": "g/t"}], [{"metal": "Cu", "value": 243, "unit": "Mlb"}, {"metal": "Ag", "value": 617, "unit": "koz"}, {"metal": "Au", "value": 64, "unit": "koz"}], "1.00% CuEq"),
    R("Opemiska out-of-pit", "Inferred", 2130000, [{"metal": "CuEq", "value": 0.88, "unit": "%"}, {"metal": "Cu", "value": 0.69, "unit": "%"}], None, "1.00% CuEq"),
], "Update", "high", False, "a third table follows the two read back; the live page records only the pit-constrained rows")

add("5d95ef00e44a", "SVM.TO", "2025-05-12", [
    R("Condor - Camp and Los Cuyes (underground)", "Indicated", 3170000),
    R("Condor - Camp and Los Cuyes (underground)", "Inferred", 12100000),
    R("Condor - Soledad and Enma (open pit)", "Indicated", 4060000),
    R("Condor - Soledad and Enma (open pit)", "Inferred", 14170000),
], "Update", "low", False, "four bullet statements read back; grades and contained metal were cut off mid-sentence")

add("4807498f1906", "OGN.V", "2025-04-07", [
    R(u"Ermitaño", "Proven", 797000, [{"metal": "Ag", "value": 85, "unit": "g/t"}, {"metal": "Au", "value": 3.65, "unit": "g/t"}], [{"metal": "Ag", "value": 2173, "unit": "koz"}, {"metal": "Au", "value": 93, "unit": "koz"}], basis="reserve"),
    R(u"Ermitaño", "Probable", 2043000, [{"metal": "Ag", "value": 38, "unit": "g/t"}, {"metal": "Au", "value": 1.61, "unit": "g/t"}], [{"metal": "Ag", "value": 2503, "unit": "koz"}, {"metal": "Au", "value": 105, "unit": "koz"}], basis="reserve"),
    R(u"Ermitaño", "Proven & Probable", 2840000, [{"metal": "Ag", "value": 51.2, "unit": "g/t"}, {"metal": "Au", "value": 2.18, "unit": "g/t"}], [{"metal": "Ag", "value": 4676, "unit": "koz"}, {"metal": "Au", "value": 199, "unit": "koz"}], basis="reserve"),
    R(u"Ermitaño", "Measured", 883000, [{"metal": "Ag", "value": 90.5, "unit": "g/t"}, {"metal": "Au", "value": 4.2, "unit": "g/t"}], [{"metal": "Ag", "value": 2570, "unit": "koz"}, {"metal": "Au", "value": 120, "unit": "koz"}]),
    R(u"Ermitaño", "Indicated", 2506000, [{"metal": "Ag", "value": 45.6, "unit": "g/t"}, {"metal": "Au", "value": 2.26, "unit": "g/t"}], [{"metal": "Ag", "value": 3690, "unit": "koz"}, {"metal": "Au", "value": 181, "unit": "koz"}]),
    R(u"Ermitaño", "Measured & Indicated", 3389000, [{"metal": "Ag", "value": 57.3, "unit": "g/t"}, {"metal": "Au", "value": 2.76, "unit": "g/t"}], [{"metal": "Ag", "value": 6260, "unit": "koz"}, {"metal": "Au", "value": 301, "unit": "koz"}]),
    R(u"Ermitaño", "Inferred", 2355000, [{"metal": "Ag", "value": 59.2, "unit": "g/t"}, {"metal": "Au", "value": 2.14, "unit": "g/t"}], [{"metal": "Ag", "value": 4480, "unit": "koz"}, {"metal": "Au", "value": 162, "unit": "koz"}]),
    R("Navidad", "Inferred", 2267000, [{"metal": "Ag", "value": 81, "unit": "g/t"}, {"metal": "Au", "value": 3.42, "unit": "g/t"}], [{"metal": "Ag", "value": 5910, "unit": "koz"}, {"metal": "Au", "value": 249, "unit": "koz"}]),
    R(u"Ermitaño and Navidad", "Total", 4622000, [{"metal": "Ag", "value": 69.9, "unit": "g/t"}, {"metal": "Au", "value": 2.77, "unit": "g/t"}], [{"metal": "Ag", "value": 10390, "unit": "koz"}, {"metal": "Au", "value": 411, "unit": "koz"}]),
], "Update", "high", True,
    "a royalty holder reporting the operator's figures. The deposit is inside the category cell on three lines -- 'Inferred Ermitaño', 'Inferred Navidad', 'Total Inferred'. Resources are stated inclusive of reserves, so the two must not be summed")

add("68fba67c3173", "DLP.V", "2025-02-27", [
    R("Aurora", "Inferred", 1050000000, [{"metal": "Cu", "value": 0.20, "unit": "%"}], [{"metal": "Cu", "value": 4650, "unit": "Mlb"}]),
], "Maiden")

add("5a0ff7597acd", "OGC.TO", "2025-02-19", [
    R("Wharekirauponga", "Indicated", 2400000, [{"metal": "Au", "value": 17.9, "unit": "g/t"}], [{"metal": "Au", "value": 1.4, "unit": "Moz"}]),
], "Update", "low", False,
    "annual reserve and resource statement covering six operations; only the Wharekirauponga line was read back. The 8.9 Moz M&I figure is a company-wide total")

add("35aedb8daea6", "AUMB.V", "2025-01-02", [
    R("True North", "Indicated", 3516000, [{"metal": "Au", "value": 4.41, "unit": "g/t"}], [{"metal": "Au", "value": 499000, "unit": "oz"}]),
    R("True North", "Inferred", 5490000, [{"metal": "Au", "value": 3.65, "unit": "g/t"}], [{"metal": "Au", "value": 644000, "unit": "oz"}]),
], "Update")

add("b68ede693cce", "PMET.TO", "2025-08-29", [
    R("Shaakichiuwaanaan CV5", "Indicated", 108000000, [{"metal": "Li2O", "value": 1.40, "unit": "%"}, {"metal": "Cs2O", "value": 0.11, "unit": "%"}, {"metal": "Ta2O5", "value": 166, "unit": "ppm"}, {"metal": "Ga", "value": 66, "unit": "ppm"}]),
    R("Shaakichiuwaanaan CV5", "Inferred", 33400000, [{"metal": "Li2O", "value": 1.33, "unit": "%"}, {"metal": "Ta2O5", "value": 155, "unit": "ppm"}]),
    R("Shaakichiuwaanaan CV13/Vega", "Indicated", 690000, [{"metal": "Cs2O", "value": 4.40, "unit": "%"}]),
    R("Shaakichiuwaanaan CV13/Vega", "Inferred", 1700000, [{"metal": "Cs2O", "value": 2.40, "unit": "%"}]),
], "Restated", "high", False, "technical report filing on the resource estimate itself, so the figures are the subject of the release")

add("fc2879d77ec5", "CNC.V", "2025-07-29", [
    R("Mann Central and Mann West", "Measured & Indicated", None, None, [{"metal": "Ni", "value": None, "unit": "t"}]),
    R("Mann Central and Mann West", "Inferred", None, None, [{"metal": "Ni", "value": 9500000, "unit": "t"}]),
], "Restated", "low", False, "one sentence read back; the Measured and Indicated nickel tonnage was cut off")

add("044036f2ce55x", "SKIP", "", [])

add("f0e000edea1e", "MLM.CN", "2023-05-24", [
    R("Purdex Zone", "Indicated", 152000, [{"metal": "Au", "value": 9.38, "unit": "g/t"}], [{"metal": "Au", "value": 45.8, "unit": "koz"}], "2.6 g/t Au"),
    R("Purdex Zone", "Inferred", 287000, [{"metal": "Au", "value": 10.43, "unit": "g/t"}], [{"metal": "Au", "value": 96.2, "unit": "koz"}], "2.6 g/t Au"),
    R("Purdex Zone - Pit 1", "Indicated", 22000, [{"metal": "Au", "value": 6.36, "unit": "g/t"}], [{"metal": "Au", "value": 4.5, "unit": "koz"}]),
    R("Purdex Zone - Pit 1", "Inferred", 3000, [{"metal": "Au", "value": 5.25, "unit": "g/t"}], [{"metal": "Au", "value": 0.5, "unit": "koz"}]),
    R("Purdex Zone - Pit 2", "Indicated", 45000, [{"metal": "Au", "value": 4.47, "unit": "g/t"}], [{"metal": "Au", "value": 6.5, "unit": "koz"}]),
    R("Purdex Zone - Pit 2", "Inferred", 7000, [{"metal": "Au", "value": 3.65, "unit": "g/t"}], [{"metal": "Au", "value": 0.8, "unit": "koz"}]),
    R("McMillan", "Total", 727200, [{"metal": "Au", "value": 12.39, "unit": "g/t"}], [{"metal": "Au", "value": 289593, "unit": "oz"}], ctx="background"),
], "Update", "low", False,
    "a cut-off sensitivity table sits between Table 1 and the pit tables and was not read back. The McMillan figures are a 1983 historical resource")

add("4aa369cc5f8d", "CCI.CN", "2022-11-01", [
    R("Chester", "Indicated", 4866000, [{"metal": "Cu", "value": 1.13, "unit": "%"}], [{"metal": "Cu", "value": 120.28, "unit": "Mlb"}, {"metal": "Pb", "value": 13.66, "unit": "Mlb"}, {"metal": "Zn", "value": 10.52, "unit": "Mlb"}, {"metal": "Ag", "value": 69000, "unit": "oz"}]),
    R("Chester", "Inferred", 1819000, [{"metal": "Cu", "value": 1.01, "unit": "%"}], [{"metal": "Cu", "value": 38.35, "unit": "Mlb"}, {"metal": "Pb", "value": 3.17, "unit": "Mlb"}, {"metal": "Zn", "value": 1.57, "unit": "Mlb"}]),
], "Update")

add("6eada4c4e1b9", "BULL.CN", "2022-04-19", [
    R("East Bull in-pit", "Indicated", 16300000, [{"metal": "PdEq", "value": 0.92, "unit": "g/t"}, {"metal": "Pd", "value": 0.49, "unit": "g/t"}], [{"metal": "PdEq", "value": 484.6, "unit": "koz"}], "C$15/t NSR"),
    R("East Bull in-pit", "Inferred", 12700000, [{"metal": "PdEq", "value": 0.90, "unit": "g/t"}, {"metal": "Pd", "value": 0.49, "unit": "g/t"}], [{"metal": "PdEq", "value": 367.8, "unit": "koz"}], "C$15/t NSR"),
    R("East Bull out-of-pit", "Indicated", 200000, [{"metal": "PdEq", "value": 1.09, "unit": "g/t"}, {"metal": "Pd", "value": 0.60, "unit": "g/t"}], [{"metal": "PdEq", "value": 7.5, "unit": "koz"}], "C$50/t NSR"),
    R("East Bull out-of-pit", "Inferred", 3600000, [{"metal": "PdEq", "value": 1.31, "unit": "g/t"}, {"metal": "Pd", "value": 0.75, "unit": "g/t"}], [{"metal": "PdEq", "value": 151.8, "unit": "koz"}], "C$50/t NSR"),
    R("East Bull", "Indicated", 16500000, [{"metal": "PdEq", "value": 0.93, "unit": "g/t"}, {"metal": "Pd", "value": 0.49, "unit": "g/t"}], [{"metal": "PdEq", "value": 492.1, "unit": "koz"}]),
    R("East Bull", "Inferred", 16300000, [{"metal": "PdEq", "value": 0.99, "unit": "g/t"}, {"metal": "Pd", "value": 0.55, "unit": "g/t"}], [{"metal": "PdEq", "value": 519.6, "unit": "koz"}]),
], "Update", "high", True,
    "three blocks at different NSR cut-offs; the last is the total and matches the headline")

S = [x for x in S if x["ticker"] != "SKIP"]
ids = [x["event_id"] for x in S]
assert len(ids) == len(set(ids)), "duplicate event_id"
out = {"set": "resources", "version": "draft-1", "label_guide": "claude/MNT_RES_LABEL_GUIDE_2026-09-17.md",
       "set_sha": "b8d96a982e0421fa0c52d20ce88991bc2520dc0d5af5e5e92da4ea866720dd1c", "items": S}
body = "{\n" + ",\n".join('  ' + json.dumps(k) + ': ' + json.dumps(v, ensure_ascii=False)
                          for k, v in out.items() if k != "items")
body += ',\n  "items": [\n' + ",\n".join("    " + json.dumps(x, ensure_ascii=False) for x in S) + "\n  ]\n}\n"
open("res_labels_draft.json", "w").write(body)
json.load(open("res_labels_draft.json"))
n_rows = sum(len(x["rows"]) for x in S)
print("items", len(S), "with rows", sum(1 for x in S if x["rows"]),
      "no-row", sum(1 for x in S if not x["rows"]), "rows", n_rows,
      "partial", sum(1 for x in S if not x["complete"]))
print("bytes", len(body), "sha256", hashlib.sha256(body.encode()).hexdigest()[:16])
