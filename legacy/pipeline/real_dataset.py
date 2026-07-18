"""Curated REAL-world dataset: Sri Lankan illicit-network graph from public reporting.

This is the deterministic OSINT layer of the real pipeline. Every node and edge is
compiled from publicly reported information (Wikipedia, court/PCoI reporting, and named
Sri Lankan news outlets) and carries a source citation plus an honest confidence tag:

    EXTRACTED  (1.0)  fact stated plainly in an official record or by named reporting
    INFERRED   (0.7)  probable link that reporting supports but has not adjudicated
    AMBIGUOUS  (0.4)  alleged / contested / uncorroborated (e.g. IS "direction")

IMPORTANT — read before using:
  * This is an ANALYTICAL model built ONLY from open, public reporting. It is not a
    determination of guilt and asserts nothing beyond what the cited sources say.
  * Confidence tags encode source strength. AMBIGUOUS edges are explicitly contested.
  * Most individuals here are deceased, convicted, or charged in matters of extensive
    public record (a terrorist attack investigated by a Presidential Commission, and
    narcotics cases reported nationally). National ID numbers are deliberately omitted.
  * The three documented networks (historical Colombo underworld, modern transnational
    narcotics, 2019 Easter/NTJ extremism) are NOT linked to each other in the public
    record. The graph keeps them separate on purpose; community detection recovering
    them as distinct cells is itself the analytical finding.

The dataset is expressed through the same Pydantic models as every other pass, so it is
validated identically (weights derived from tags, temporal windows checked, IDs slugged).
"""

from __future__ import annotations

from legacy.pipeline.models import (
    ConfidenceTag,
    CriminalNode,
    ExtractionMethod,
    ExtractionResult,
    LayerType,
    NodeType,
    TemporalEdge,
)

# --- Source citations (short key -> (publication, url)) -----------------------
SOURCES: dict[str, tuple[str, str]] = {
    "wiki_mobsters": (
        "Wikipedia — List of Sri Lankan mobsters",
        "https://en.wikipedia.org/wiki/List_of_Sri_Lankan_mobsters",
    ),
    "wiki_easter": (
        "Wikipedia — 2019 Sri Lanka Easter bombings",
        "https://en.wikipedia.org/wiki/2019_Sri_Lanka_Easter_bombings",
    ),
    "adaderana_madush": (
        "Ada Derana — 'Makandure Madush arrested in Dubai'",
        "http://www.adaderana.lk/news/53068/makandure-madush-arrested-in-dubai",
    ),
    "dm_imran": (
        "Daily Mirror — 'Kanjipani Imran, three others deported from Dubai'",
        "https://www.dailymirror.lk/breaking-news/Kanjipani-Imran-three-others-deported-from-Dubai/108-164623",
    ),
    "dbsj_madush": (
        "dbsjeyaraj.com — 'Downfall in Dubai of Sri Lanka's Most Wanted Drug Dealer Makandure Madush'",
        "https://dbsjeyaraj.com/dbsj/?p=62890",
    ),
    "dm_madush_arrest": (
        "Daily Mirror — 'Who was behind the arrest of Makandure Madush?'",
        "https://www.dailymirror.lk/news-features/Who-was-behind-the-arrest-of-Makandure-Madush-/131-162475",
    ),
    "newsfirst_harak": (
        "News First — 'Underworld gangster Harak Kata extradited to Sri Lanka from Madagascar'",
        "https://www.newsfirst.lk/2023/03/15/underworld-gangster-harak-kata-extradited-to-sri-lanka-from-madagascar",
    ),
    "timesaddu_harak": (
        "Times of Addu — 'Sri Lankan drug trafficker Harak Kata with links to Maldives arrested in Dubai'",
        "https://timesofaddu.com/2022/08/13/sri-lankan-drug-trafficker-harak-kata-with-links-to-maldives-arrested-in-dubai/",
    ),
    "lnw_boossa": (
        "Lanka News Web — 'Mobile phone and accessories found in cells of notorious criminals at Boossa Prison'",
        "https://lankanewsweb.net/archives/63756/",
    ),
    "jamestown_zahran": (
        "Jamestown Foundation — 'The Mastermind of the Sri Lankan Easter Sunday Attacks: Zahran Hashim'",
        "https://jamestown.org/brief/the-mastermind-of-the-sri-lankan-easter-sunday-attacks-a-brief-sketch-of-mohammed-zahran-hashim-of-national-thowheeth-jamaath/",
    ),
    "adaderana_pcoi": (
        "Ada Derana — 'Zahran planned to launch Easter attack using 20 bombers, PCoI hears'",
        "https://adaderana.lk/news/68204",
    ),
    "tamilguardian_80": (
        "Tamil Guardian — 'Drug kingpin killed to protect the identity of 80 politicians claims JVP MP'",
        "https://www.tamilguardian.com/content/drug-kingpin-killed-protect-identity-80-politicians-claims-jvp-mp",
    ),
}


def _cite(key: str) -> str:
    pub, _url = SOURCES[key]
    return pub


# --- Entity name constants (single source of truth => no dangling edges) -------
# Modern transnational narcotics network
MADUSH = "Makandure Madush"
IMRAN = "Kanjipani Imran"
ANGODA = "Angoda Lokka"
HARAK = "Harak Kata"
WELESUDA = "Wele Suda"
KALUSAGARA = "Kalu Sagara"
SAMAYAN = "Ranale Samayan"
KUDU_SALINDU = "Kudu Salindu"
GANEMULLA = "Ganemulla Sanjeewa"
KOSGODA_SUJEE = "Kosgoda Sujee"
MERRILL = "Kirulapone Merrill"
SIDDIQUE = "Siddique"

# Historical Colombo underworld (1980s–2000s feuds)
SOTHTHI = "Soththi Upali"
CHINTHAKA = "Chinthaka Amarasinghe"
DHAMMIKA = "Dhammika Amarasinghe"
KALU_AJITH = "Kalu Ajith"
NAWALA = "Nawala Nihal"
KADUWELA = "Kaduwela Wasantha"
MORATU = "Moratu Saman"
# LTTE-linked drug/assassination trio
OLCOTT = "Olcott"
KIMBULA = "Kimbula-Ela Guna"
THELBALA = "Thel Bala"

# 2019 Easter Sunday / NTJ extremist network
ZAHRAN = "Zahran Hashim"
RILWAN = "Rilwan Hashim"
ZAINEE = "Zainee Hashim"
NAUFER = "Naufer Moulavi"
INSHAF = "Inshaf Ahmed"
ILHAM = "Ilham Ahmed"
LATHEEF = "Abdul Latheef Jameel"
AZAM = "Mohamed Azam"
NASSAR = "Mohamed Nassar"
HASTHUN = "Hasthun"
MUAD = "Alawdeen Ahmed Muad"
MILHAN = "Ahmed Milhan"
ARMY_MOHIDEEN = "Army Mohideen"
FATHIMA = "Fathima Ilham"
PULASTHINI = "Pulasthini Rajendran"
ABU_HIND = "Abu Hind"
NTJ = "National Thowheeth Jamaath"
JMI = "Jammiyathul Millathu Ibrahim"
ISIS = "Islamic State"


def _n(
    name: str,
    *,
    aliases: list[str] | None = None,
    affiliations: list[str] | None = None,
    org: bool = False,
    src: str,
    note: str,
) -> CriminalNode:
    return CriminalNode(
        name=name,
        aliases=aliases or [],
        affiliations=affiliations or [],
        node_type=NodeType.ORGANIZATION if org else NodeType.PERSON,
        source_file=_cite(src),
        source_excerpt=note,
    )


def _e(
    source: str,
    target: str,
    relation: str,
    layer: LayerType,
    confidence: ConfidenceTag,
    *,
    src: str,
    excerpt: str,
    start: str | None = None,
    end: str | None = None,
    location: str | None = None,
) -> TemporalEdge:
    return TemporalEdge(
        source=source,
        target=target,
        relation=relation,
        layer=layer,
        confidence=confidence,
        start_date=start,
        end_date=end,
        location=location,
        source_file=_cite(src),
        source_excerpt=excerpt,
        extraction_method=ExtractionMethod.CURATED,
    )


# Shorthands
EXTRACTED, INFERRED, AMBIGUOUS = (
    ConfidenceTag.EXTRACTED,
    ConfidenceTag.INFERRED,
    ConfidenceTag.AMBIGUOUS,
)
IDEO, FIN, PRISON, TRANS = (
    LayerType.IDEOLOGICAL,
    LayerType.FINANCIAL,
    LayerType.PRISON_CO_LOCATION,
    LayerType.TRANSNATIONAL,
)


# =============================================================================
# 1. MODERN TRANSNATIONAL NARCOTICS NETWORK
# =============================================================================
_NARCOTICS_NODES = [
    _n(MADUSH, aliases=["Samarasinghe Arachchige Madush Lakshitha"],
       affiliations=["Madush drug network"], src="dbsj_madush",
       note="Drug kingpin; ran a Dubai-based narcotics network. Arrested in Dubai 4 Feb 2019, "
            "returned to Sri Lanka 5 May 2019 under the PTA, shot dead in police custody 20 Oct 2020."),
    _n(IMRAN, aliases=["Mohamed Najim Mohamed Imran"], affiliations=["Madush drug network"],
       src="dm_imran",
       note="Colombo underworld figure; arrested with Madush in Dubai 4 Feb 2019 and deported to Sri Lanka."),
    _n(ANGODA, aliases=["Maddumage Chandana Lasantha Perera"], affiliations=["Angoda Lokka network"],
       src="wiki_mobsters",
       note="Drug lord; reportedly died of a heart attack in Coimbatore, India in 2020 while directing operations from abroad."),
    _n(HARAK, aliases=["Nadun Chinthaka Wickramaratne"], affiliations=["Harak Kata network"],
       src="newsfirst_harak",
       note="Heroin trafficker with an international network (Dubai, Malaysia, Maldives, Seychelles, Madagascar); "
            "arrested in Madagascar and extradited to Sri Lanka 15 Mar 2023; held under the PTA."),
    _n(WELESUDA, aliases=["Gampola Vidanelage Samantha Kumara"], affiliations=["Wele Suda network"],
       src="wiki_mobsters",
       note="Major heroin trafficker; arrested in Pakistan (Karachi) in Feb 2015 and extradited; "
            "continued to run operations from prison. Serving a life sentence."),
    _n(KALUSAGARA, affiliations=["Madush drug network (former)"], src="dm_madush_arrest",
       note="One-time associate of Madush who reportedly tipped off Dubai Police and the Sri Lankan STF to his location."),
    _n(SAMAYAN, aliases=["Aruna Damith Udayanga"], src="wiki_mobsters",
       note="Underworld gang leader; killed in 2017, reportedly by the rival gang of Angoda Lokka and Makandure Madush."),
    _n(KUDU_SALINDU, affiliations=["Harak Kata network"], src="newsfirst_harak",
       note="Organized-crime suspect arrested in Madagascar alongside Harak Kata and brought to Sri Lanka in March 2023."),
    _n(GANEMULLA, affiliations=["Organized crime"], src="lnw_boossa",
       note="Organized-crime and drug-trafficking convict; a smartphone and accessories were found in his Boossa Prison cell."),
    _n(KOSGODA_SUJEE, affiliations=["Madush drug network (former)"], src="dbsj_madush",
       note="Named among the group that helped Madush establish himself in Dubai before falling out with him."),
    _n(MERRILL, aliases=["Kirulapone Merrill"], affiliations=["Madush drug network (former)"], src="dbsj_madush",
       note="Named among the group that helped Madush establish himself in Dubai before falling out with him."),
    _n(SIDDIQUE, affiliations=["Madush drug network (former)"], src="dbsj_madush",
       note="Named among the group that helped Madush establish himself in Dubai before falling out with him."),
]

_NARCOTICS_EDGES = [
    _e(MADUSH, IMRAN, "co_arrested_with", TRANS, EXTRACTED, src="adaderana_madush",
       excerpt="Madush was arrested in Dubai on 4 Feb 2019; Kanjipani Imran was among those arrested with him and later deported.",
       start="2019-02-04", end="2019-02-04", location="Dubai, UAE"),
    _e(MADUSH, IMRAN, "partnered_with", TRANS, INFERRED, src="dbsj_madush",
       excerpt="Imran had partnered with Makandure Madush to build a syndicate controlling maritime trafficking routes through the Indian Ocean.",
       location="Indian Ocean routes"),
    _e(MADUSH, ANGODA, "allied_with", FIN, INFERRED, src="wiki_mobsters",
       excerpt="Ranale Samayan was killed in 2017 by the rival gang of Angoda Lokka and Makandure Madush — indicating an operational alliance between them.",
       start="2017-01-01"),
    _e(ANGODA, SAMAYAN, "ordered_killing_of", FIN, INFERRED, src="wiki_mobsters",
       excerpt="Samayan's death (2017) is attributed to the rival gang of Angoda Lokka and Makandure Madush.",
       start="2017-01-01", end="2017-01-01"),
    _e(MADUSH, SAMAYAN, "ordered_killing_of", FIN, INFERRED, src="wiki_mobsters",
       excerpt="Samayan's death (2017) is attributed to the rival gang of Angoda Lokka and Makandure Madush.",
       start="2017-01-01", end="2017-01-01"),
    _e(ANGODA, HARAK, "close_associate_of", FIN, INFERRED, src="timesaddu_harak",
       excerpt="Harak Kata is described as a close associate of the slain underworld don 'Angoda Lokka'."),
    _e(HARAK, KUDU_SALINDU, "co_arrested_with", TRANS, EXTRACTED, src="newsfirst_harak",
       excerpt="Harak Kata and Kudu Salindu were arrested in Madagascar and brought to Sri Lanka in March 2023.",
       start="2023-03-15", end="2023-03-15", location="Madagascar"),
    _e(KALUSAGARA, MADUSH, "rival_of", FIN, INFERRED, src="dm_madush_arrest",
       excerpt="Kalu Sagara was a one-time friend of Madush; drug-trade rivalry turned them against each other."),
    _e(KALUSAGARA, MADUSH, "tipped_off_police_on", FIN, INFERRED, src="dm_madush_arrest",
       excerpt="Kalu Sagara reportedly tipped off Dubai Police and the Sri Lankan STF about Madush's location, leading to his arrest.",
       start="2019-02-01", end="2019-02-04", location="Dubai, UAE"),
    _e(WELESUDA, MADUSH, "helped_establish_in_dubai", TRANS, INFERRED, src="dbsj_madush",
       excerpt="Wele Suda, Kosgoda Sujee, Kirulapone Merrill and Siddique had helped Madush set up in Dubai.",
       location="Dubai, UAE"),
    _e(KOSGODA_SUJEE, MADUSH, "helped_establish_in_dubai", TRANS, INFERRED, src="dbsj_madush",
       excerpt="Wele Suda, Kosgoda Sujee, Kirulapone Merrill and Siddique had helped Madush set up in Dubai.",
       location="Dubai, UAE"),
    _e(MERRILL, MADUSH, "helped_establish_in_dubai", TRANS, INFERRED, src="dbsj_madush",
       excerpt="Wele Suda, Kosgoda Sujee, Kirulapone Merrill and Siddique had helped Madush set up in Dubai.",
       location="Dubai, UAE"),
    _e(SIDDIQUE, MADUSH, "helped_establish_in_dubai", TRANS, INFERRED, src="dbsj_madush",
       excerpt="Wele Suda, Kosgoda Sujee, Kirulapone Merrill and Siddique had helped Madush set up in Dubai.",
       location="Dubai, UAE"),
    _e(WELESUDA, MADUSH, "conspired_against", FIN, INFERRED, src="dbsj_madush",
       excerpt="The same group, feeling sidelined by Madush, was reportedly involved in setting him up for arrest.",
       start="2019-02-01", end="2019-02-04"),
    _e(KOSGODA_SUJEE, MADUSH, "conspired_against", FIN, INFERRED, src="dbsj_madush",
       excerpt="The same group, feeling sidelined by Madush, was reportedly involved in setting him up for arrest.",
       start="2019-02-01", end="2019-02-04"),
    _e(MERRILL, MADUSH, "conspired_against", FIN, INFERRED, src="dbsj_madush",
       excerpt="The same group, feeling sidelined by Madush, was reportedly involved in setting him up for arrest.",
       start="2019-02-01", end="2019-02-04"),
    _e(SIDDIQUE, MADUSH, "conspired_against", FIN, INFERRED, src="dbsj_madush",
       excerpt="The same group, feeling sidelined by Madush, was reportedly involved in setting him up for arrest.",
       start="2019-02-01", end="2019-02-04"),
    # Real prison co-location, reported by a named outlet (curated, not from the regex pass).
    _e(WELESUDA, GANEMULLA, "co_located_in_prison_with", PRISON, EXTRACTED, src="lnw_boossa",
       excerpt="An STF sweep recovered a smartphone and accessories concealed in the cells of two notorious inmates, "
               "'Ganemulla Sanjeewa' and 'Wele Suda', at Boossa high-security prison.",
       location="Boossa Prison"),
]


# =============================================================================
# 2. HISTORICAL COLOMBO UNDERWORLD (1980s–2000s)
# =============================================================================
_HISTORICAL_NODES = [
    _n(SOTHTHI, aliases=["Arambawelage Don Upali Ranjith"], src="wiki_mobsters",
       note="Underworld figure active 1970–1998; allied with political patrons of the era. Killed 17 Dec 1998."),
    _n(CHINTHAKA, aliases=["Usliyanage Chinthaka Nalin Perera"], src="wiki_mobsters",
       note="Underworld figure who reportedly sought to avenge his father's killing by Soththi Upali's faction; killed 1996."),
    _n(DHAMMIKA, aliases=["Dhammika Amarasinghe"], src="wiki_mobsters",
       note="Brother of Chinthaka Amarasinghe; active 1990s–2004. Killed inside Colombo Magistrate's Court in Jan 2004."),
    _n(KALU_AJITH, aliases=["Ajith Dhammika"], src="wiki_mobsters",
       note="Gang leader active 1980s–1997; his gang was blamed for the 1996 killing of Chinthaka Amarasinghe. Killed 16 Jul 1997."),
    _n(NAWALA, aliases=["Koswattage Donald Nihal Wickremasinghe"], src="wiki_mobsters",
       note="Described as a godfather of the Colombo underworld; blamed for the 1997 killing of Kalu Ajith. Died 2006."),
    _n(KADUWELA, aliases=["Wasantha Darmasiri Jayarathna"], src="wiki_mobsters",
       note="Underworld figure reportedly allied with Chinthaka Amarasinghe and Kalu Ajith. Killed 26 May 2002."),
    _n(MORATU, aliases=["Moratu Saman"], src="wiki_mobsters",
       note="Underworld figure once allied with Dhammika Amarasinghe before a violent falling-out. Died 2003."),
    _n(OLCOTT, aliases=["Jayakody Arachchige Ruwan Perera"], affiliations=["LTTE (alleged)"], src="wiki_mobsters",
       note="Heroin trafficker linked to a failed 1999 LTTE assassination attempt on President Chandrika Kumaratunga; "
            "lived in exile in Tamil Nadu. Killed in an STF raid in Sept 2010."),
    _n(KIMBULA, aliases=["Sinniah Gunasekeran"], affiliations=["LTTE (alleged)"], src="wiki_mobsters",
       note="Major drug dealer with LTTE links; involved in the failed 1999 assassination attempt on President Kumaratunga; "
            "arrested in Tamil Nadu in 2008."),
    _n(THELBALA, aliases=["Ganeshalingam Saipriyan"], affiliations=["LTTE (alleged)"], src="wiki_mobsters",
       note="Jaffna-region drug dealer linked to the failed 1999 assassination attempt on President Kumaratunga. Died 2017."),
]

_HISTORICAL_EDGES = [
    _e(CHINTHAKA, SOTHTHI, "avenging_rival_of", FIN, INFERRED, src="wiki_mobsters",
       excerpt="Chinthaka Amarasinghe was reportedly motivated by avenging his father's death at the hands of Soththi Upali's faction."),
    _e(KALU_AJITH, CHINTHAKA, "ordered_killing_of", FIN, INFERRED, src="wiki_mobsters",
       excerpt="Chinthaka Amarasinghe (d. 1996) was killed by Kalu Ajith's gang.",
       start="1996-01-01", end="1996-01-01"),
    _e(NAWALA, KALU_AJITH, "ordered_killing_of", FIN, INFERRED, src="wiki_mobsters",
       excerpt="Kalu Ajith was killed on 16 Jul 1997; the killing is attributed to Nawala Nihal.",
       start="1997-07-16", end="1997-07-16"),
    _e(DHAMMIKA, CHINTHAKA, "sibling_of", FIN, EXTRACTED, src="wiki_mobsters",
       excerpt="Dhammika Amarasinghe was the brother of Chinthaka Amarasinghe."),
    _e(SOTHTHI, DHAMMIKA, "killed_family_of", FIN, INFERRED, src="wiki_mobsters",
       excerpt="Sixteen members of Dhammika Amarasinghe's family were reportedly killed by Soththi Upali's gang."),
    _e(MORATU, DHAMMIKA, "former_ally_turned_rival_of", FIN, INFERRED, src="wiki_mobsters",
       excerpt="Moratu Saman was once allied with Dhammika Amarasinghe before falling out; Dhammika reportedly tried to kill him in 2002."),
    _e(KADUWELA, CHINTHAKA, "allied_with", FIN, INFERRED, src="wiki_mobsters",
       excerpt="Kaduwela Wasantha was reportedly allied with Chinthaka Amarasinghe and Kalu Ajith."),
    _e(KADUWELA, KALU_AJITH, "allied_with", FIN, INFERRED, src="wiki_mobsters",
       excerpt="Kaduwela Wasantha was reportedly allied with Chinthaka Amarasinghe and Kalu Ajith."),
    # LTTE-linked trio: 1999 assassination plot + Tamil Nadu narcotics base
    _e(OLCOTT, KIMBULA, "co_conspirator_in_plot_with", IDEO, INFERRED, src="wiki_mobsters",
       excerpt="Olcott, Kimbula-Ela Guna and Thel Bala were linked to the failed 1999 LTTE assassination attempt on President Kumaratunga.",
       start="1999-01-01"),
    _e(OLCOTT, THELBALA, "co_conspirator_in_plot_with", IDEO, INFERRED, src="wiki_mobsters",
       excerpt="Olcott, Kimbula-Ela Guna and Thel Bala were linked to the failed 1999 LTTE assassination attempt on President Kumaratunga.",
       start="1999-01-01"),
    _e(KIMBULA, THELBALA, "co_conspirator_in_plot_with", IDEO, INFERRED, src="wiki_mobsters",
       excerpt="Olcott, Kimbula-Ela Guna and Thel Bala were linked to the failed 1999 LTTE assassination attempt on President Kumaratunga.",
       start="1999-01-01"),
    _e(KIMBULA, OLCOTT, "ran_narcotics_from_tamil_nadu_with", TRANS, INFERRED, src="wiki_mobsters",
       excerpt="Both fled to Tamil Nadu and were reported to monitor / run drug trafficking into Sri Lanka from India."),
]


# =============================================================================
# 3. 2019 EASTER SUNDAY / NTJ EXTREMIST NETWORK
# =============================================================================
_EXTREMISM_NODES = [
    _n(ZAHRAN, aliases=["Mohamed Hashim Mohamed Zahran", "Mohammed Zahran Hashim"],
       affiliations=[NTJ], src="jamestown_zahran",
       note="Founder of the National Thowheeth Jama'ath and suspected ringleader of the 21 Apr 2019 Easter attacks; "
            "suicide bomber at the Shangri-La Hotel."),
    _n(RILWAN, affiliations=[NTJ], src="wiki_easter",
       note="Brother of Zahran Hashim; reportedly helped build explosives. Killed in the Sainthamaruthu raid on 26 Apr 2019."),
    _n(ZAINEE, affiliations=[NTJ], src="wiki_easter",
       note="Brother of Zahran Hashim; named among those directly linked to the attack network."),
    _n(NAUFER, aliases=["Mohamed Naufer", "Naufer Moulavi"], affiliations=[NTJ], src="adaderana_pcoi",
       note="Named by the Minister of Public Security, after the PCoI report, as the mastermind of the Easter attacks; in custody."),
    _n(INSHAF, aliases=["Mohamed Ibrahim Inshaf Ahamed"], affiliations=[NTJ], src="wiki_easter",
       note="Suicide bomber at the Cinnamon Grand; owned the Colossus Copper factory reportedly used to fabricate suicide vests."),
    _n(ILHAM, aliases=["Mohamed Ibrahim Ilham Ahamed"], affiliations=[NTJ], src="wiki_easter",
       note="Suicide bomber at the Shangri-La Hotel; younger brother of Inshaf Ahmed."),
    _n(LATHEEF, aliases=["Abdul Lathif Jameel Mohammed"], affiliations=[NTJ], src="wiki_easter",
       note="Suicide bomber (Tropical Inn, Dehiwala); had been investigated in 2014 by an Australian Joint Counter Terrorism "
            "Team over reported ISIS links via operative Neil Prakash."),
    _n(AZAM, aliases=["Mohamed Azam Mohamed Mubarak"], affiliations=[NTJ], src="wiki_easter",
       note="Suicide bomber at the Kingsbury Hotel; NTJ member."),
    _n(NASSAR, aliases=["Mohamed Nassar Mohamed Asad"], affiliations=[NTJ], src="wiki_easter",
       note="Suicide bomber at Zion Church, Batticaloa; NTJ member."),
    _n(HASTHUN, aliases=["Atchchi Muhammadu Muhammadu Hasthun"], affiliations=[NTJ], src="wiki_easter",
       note="Suicide bomber at St. Sebastian's Church, Negombo; husband of Pulasthini Rajendran."),
    _n(MUAD, aliases=["Alawdeen Ahmed Muad"], affiliations=[NTJ], src="wiki_easter",
       note="Suicide bomber at St. Anthony's Shrine, Colombo; NTJ member."),
    _n(MILHAN, aliases=["Hayathu Mohamed Ahmed Milhan"], affiliations=[NTJ], src="wiki_easter",
       note="Suspected NTJ figure, reportedly deported from the Middle East and expected to be a successor leader."),
    _n(ARMY_MOHIDEEN, affiliations=[NTJ], src="wiki_easter",
       note="Reportedly provided military-style training to the attackers."),
    _n(FATHIMA, aliases=["Fathima Ilham"], affiliations=[NTJ], src="wiki_easter",
       note="Wife of Ilham Ahmed; detonated explosives during the Dematagoda raid on 26 Apr 2019, killing herself, "
            "her children and three police officers."),
    _n(PULASTHINI, aliases=["Sarah"], affiliations=[NTJ], src="wiki_easter",
       note="Wife of the bomber Hasthun; killed in the Sainthamaruthu raid on 26 Apr 2019."),
    _n(ABU_HIND, affiliations=["Islamic State (alleged)"], src="wiki_easter",
       note="A contact in India with whom Zahran reportedly maintained regular phone communication from 2018."),
    _n(NTJ, aliases=["NTJ", "National Thowheeth Jama'ath"], org=True, src="wiki_easter",
       note="Local militant Islamist group founded by Zahran Hashim; designated a terrorist organisation on 27 Apr 2019."),
    _n(JMI, aliases=["JMI"], org=True, src="wiki_easter",
       note="Jammiyathul Millathu Ibrahim — a splinter group designated a terrorist organisation alongside the NTJ on 27 Apr 2019."),
    _n(ISIS, aliases=["ISIS", "IS", "Islamic State of Iraq and Syria"], org=True, src="wiki_easter",
       note="Islamic State; its Amaq agency claimed the attacks, but the CID found no evidence of direct IS operational involvement."),
]


def _member(name: str, confidence: ConfidenceTag = EXTRACTED, note: str | None = None) -> TemporalEdge:
    return _e(name, NTJ, "member_of", IDEO, confidence, src="wiki_easter",
              excerpt=note or f"{name} is named as a member of the National Thowheeth Jama'ath attack network.")


_EXTREMISM_EDGES = [
    _e(ZAHRAN, NTJ, "founded", IDEO, EXTRACTED, src="jamestown_zahran",
       excerpt="The National Thowheeth Jama'ath was founded by Zahran Hashim.",
       start="2014-01-01"),
    _e(ZAHRAN, RILWAN, "sibling_co_attacker_of", IDEO, EXTRACTED, src="wiki_easter",
       excerpt="Zahran Hashim's two brothers, Rilwan Hashim and Zainee Hashim, were directly linked to the attack network."),
    _e(ZAHRAN, ZAINEE, "sibling_co_attacker_of", IDEO, EXTRACTED, src="wiki_easter",
       excerpt="Zahran Hashim's two brothers, Rilwan Hashim and Zainee Hashim, were directly linked to the attack network."),
    _e(NAUFER, ZAHRAN, "co_masterminded_attacks_with", IDEO, INFERRED, src="adaderana_pcoi",
       excerpt="After the PCoI report, the Minister of Public Security stated that Muhammed Naufer was the mastermind of the Easter attacks, alongside Zahran."),
    _member(NAUFER, note="Muhammed Naufer, named as the mastermind, was a leading figure of the NTJ network."),
    _member(RILWAN),
    _member(ZAINEE),
    _member(INSHAF),
    _member(ILHAM),
    _member(LATHEEF),
    _member(AZAM),
    _member(NASSAR),
    _member(HASTHUN),
    _member(MUAD),
    _member(PULASTHINI, confidence=INFERRED,
            note="Pulasthini Rajendran (Sarah), wife of the bomber Hasthun, was part of the NTJ network and died in the Sainthamaruthu raid."),
    _member(FATHIMA, confidence=INFERRED,
            note="Fathima Ilham, wife of Ilham Ahmed, was part of the network and detonated during the Dematagoda raid."),
    _e(INSHAF, ILHAM, "sibling_co_attacker_of", IDEO, EXTRACTED, src="wiki_easter",
       excerpt="Ilham Ahmed was the younger brother of Inshaf Ahmed; both were suicide bombers."),
    _e(INSHAF, NTJ, "financed_and_supplied_materiel_to", FIN, INFERRED, src="wiki_easter",
       excerpt="Inshaf Ahmed owned the Colossus Copper manufacturing business, reportedly used to fabricate suicide vests using bolts and screws.",
       end="2019-04-21"),
    _e(ARMY_MOHIDEEN, NTJ, "provided_military_training_to", IDEO, INFERRED, src="wiki_easter",
       excerpt="Army Mohideen reportedly provided military training to the perpetrators."),
    _e(ZAHRAN, ABU_HIND, "communicated_with", TRANS, INFERRED, src="wiki_easter",
       excerpt="Zahran Hashim maintained regular phone communication with Abu Hind from India; per his wife Hadiya's testimony this began as early as 2018.",
       start="2018-01-01", end="2019-04-21", location="India"),
    _e(NTJ, ISIS, "pledged_allegiance_to", IDEO, AMBIGUOUS, src="wiki_easter",
       excerpt="Amaq released a video of eight bombers pledging allegiance to Abu Bakr al-Baghdadi, but the CID found no evidence of direct IS operational involvement.",
       start="2019-04-23"),
    _e(ZAHRAN, ISIS, "pledged_allegiance_to", IDEO, AMBIGUOUS, src="wiki_easter",
       excerpt="Zahran Hashim appeared in the IS pledge-of-allegiance video; direct IS involvement was not established by the CID.",
       start="2019-04-23"),
    _e(LATHEEF, ISIS, "suspected_foreign_is_contact_of", TRANS, AMBIGUOUS, src="wiki_easter",
       excerpt="Abdul Latheef was investigated in 2014 by an Australian Joint Counter Terrorism Team over reported ISIS links via operative Neil Prakash.",
       start="2014-01-01"),
    _e(MILHAN, NTJ, "suspected_successor_leader_of", IDEO, AMBIGUOUS, src="wiki_easter",
       excerpt="Ahmed Milhan was a suspected mastermind reportedly expected to become a successor NTJ leader."),
    _e(HASTHUN, PULASTHINI, "spousal_co_attacker_of", IDEO, INFERRED, src="wiki_easter",
       excerpt="Pulasthini Rajendran (Sarah) was the wife of the bomber Hasthun; she was killed in the Sainthamaruthu raid."),
    _e(ILHAM, FATHIMA, "spousal_co_attacker_of", IDEO, INFERRED, src="wiki_easter",
       excerpt="Fathima Ilham was the pregnant wife of Ilham Ahmed; she detonated explosives during the Dematagoda raid."),
    _e(JMI, NTJ, "splinter_affiliate_of", IDEO, INFERRED, src="wiki_easter",
       excerpt="Jammiyathul Millathu Ibrahim (JMI) was a splinter group designated a terrorist organisation alongside the NTJ."),
]


def build_curated_network() -> ExtractionResult:
    """The full curated real-world OSINT graph (validated by the Pydantic models)."""
    return ExtractionResult(
        nodes=[*_NARCOTICS_NODES, *_HISTORICAL_NODES, *_EXTREMISM_NODES],
        edges=[*_NARCOTICS_EDGES, *_HISTORICAL_EDGES, *_EXTREMISM_EDGES],
    )


def sources_for_meta() -> list[dict]:
    """Sources as a list of {key, publication, url} for the UI / graph metadata."""
    return [{"key": k, "publication": pub, "url": url} for k, (pub, url) in SOURCES.items()]


if __name__ == "__main__":
    net = build_curated_network()
    dangling = net.dangling_edges()
    print(f"curated network: {len(net.nodes)} nodes, {len(net.edges)} edges")
    print(f"dangling edges (should be 0): {len(dangling)}")
    for e in dangling:
        print("  DANGLING:", e.source, "->", e.target, e.relation)
