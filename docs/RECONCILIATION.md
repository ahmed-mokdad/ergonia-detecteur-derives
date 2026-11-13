# Réconciliation deriv.io / Ergonia — défi 4 « Le détecteur de dérives »

Energ-IACK 2026, analyse du 13.11.2026. Données : lots ouverts Rive-Claire 1, 4 et 5 seulement (CC BY 4.0,
« Energ-IA Transition, Energ-IACK 2026 » ; température et rayonnement : MétéoSuisse, Genève-Cointrin).
Scripts rejouables : dépôt deriv.io, dossier `analyse/` (`q1_…q7_*.py`) ; aucune sortie ni donnée n'est versée
ici. Le moteur d'Ergonia est rejoué
tel quel en version 1.0.0 (9 dérives sur 11, 7 fausses alertes sur 18, délai médian 8 jours : reproduit).

**Sigles.** COP : coefficient de performance d'une pompe à chaleur (chaleur produite / électricité). PAC : pompe à
chaleur. CAD : chauffage à distance. PV : photovoltaïque. kWc : kilowatt-crête. DJ : degrés-jours (ici 20/12, feuille
Ref_Climat). CUSUM : somme cumulée des écarts (règle de détection d'Ergonia). PCS : pouvoir calorifique supérieur
du gaz. ACV : analyse du cycle de vie. KBOB : Conférence de coordination des services de la construction et des
immeubles des maîtres d'ouvrage publics (Suisse). OFEV : Office fédéral de l'environnement. SIG : Services
industriels de Genève. SIR : distributeur fictif de Rive-Claire. GO : garantie d'origine. HT / TTC : hors taxe /
toutes taxes comprises. ΔT : écart de température aller-retour.

**Convention.** *Mesuré* = calculé directement sur les lots. *Estimé* = sorti d'un modèle dont l'hypothèse est
dite. *Supposé* = hypothèse non vérifiable ici.

**Seuils.** Aucun seuil de deriv.io ni d'Ergonia n'a été modifié. Les règles nouvelles de la partie 2 ont leurs seuils
écrits dans le script avant le premier lancement ; elles ont été *conçues* en sachant quelles dérives étaient
manquées (c'est la question), ce qui est un biais. Un seul changement après coup, sur un chiffrage et non sur un
seuil : la borne basse de la ventilation de S26 (partie 4), revue après avoir vu que le reste du site baissait.

---

## 1. deriv.io rejoué en temps réel

Règle de deriv.io inchangée : un mois est hors tolérance si |lot − v2| > 0,75 % (2,5 % pour l'injection de mai à
juillet). Si la référence du mois n'est connue qu'à sa clôture, le signalement tombe le dernier jour du premier mois
hors tolérance (J+0). Hypothèse *supposée* plus réaliste : référence publiée 10 jours après (J+10).

| Dérive | Début deriv.io | Début contrôle Ergonia | 1er mois hors tolérance | Signalé (J+0) | Délai J+0 vs deriv.io | vs contrôle | Ergonia v1.0.0 |
|---|---|---|---|---|---|---|---|
| S01 électricité | 30.04 | 02.05 | avril (+1,9 %) | 30.04 | 0 j | −2 j | 11 j |
| S05 électricité | 28.06 | 28.06 | juin (+1,3 %) | 30.06 | 2 j | 2 j | 12 j |
| S05 eau | 07.07 | 07.07 | juillet (+146 %) | 31.07 | 24 j | 24 j | −7 j (alerte antérieure) |
| S13 électricité | 17.11 | 17.11 | novembre (+14 %) | 30.11 | 13 j | 13 j | −133 j (alerte antérieure) |
| S26 gaz | 16.10 | 30.09 | octobre (+9 %) | 31.10 | 15 j | 31 j | **manquée** |
| S30 électricité | 04.06 | 05.06 | juin (+5,5 %) | 30.06 | 26 j | 25 j | 62 j |
| S31 électricité | 02.10 | 01.11 | octobre (+1,5 %) | 31.10 | 29 j | −1 j | **manquée** |
| S32 électricité | 28.03 | 17.05 | mars (+1,6 %) | 31.03 | 3 j | −47 j | 166 j |
| S32 PV | 19.05 | 24.05 | mai (−13 %) | 31.05 | 12 j | 7 j | 7 j |
| S37 CAD | 03.11 | 18.11 | novembre (+18 %) | 30.11 | 27 j | 12 j | −65 j (alerte antérieure) |
| S26 injection | 04.08 | 04.08 | août (−72 %) | 31.08 | 27 j | 27 j | 8 j |

Hors rapprochement : le COP de S09 (test physique) se lit à la clôture de janvier, soit 30 jours ; la température
de retour de S06 se lit à l'heure, sans référence mensuelle (délai non rejoué ici).

**Médianes (mesuré).** deriv.io : 14 jours à J+0 (10 dérives, ses propres débuts), 12 jours contre les débuts de
contrôle d'Ergonia (11 dérives), 22 jours à J+10. Ergonia : 8 jours publiés, mais cette médiane compte trois délais
négatifs (alertes commencées 7 à 133 jours *avant* la dérive, qui la recouvrent sans la prouver) et exclut les deux
manquées. Médiane des seuls délais positifs : 11,5 jours ; sur les 11 dérives en comptant les manquées comme
infinies : 11 jours. **À débuts égaux, les deux projets signalent en 1 à 2 semaines** ; deriv.io est en avance sur les
dérives lentes (S30, S32 : 25 et −47 jours contre 62 et 166), Ergonia sur les ruptures nettes en début de mois
(S26 injection, S05 électricité).

Attention à la vérité de contrôle elle-même : elle sort d'un CUSUM à seuil 4 % sur la v2, donc elle date tard les
rampes. Pour S32 électricité, la v2 est déjà à +1,6 % en mars et +3,0 % en avril (mesuré) : le début réel est fin
mars (deriv.io), pas le 17 mai. Même chose pour S31 (octobre à +1,5 %).

**Ce que le « 100 % » de deriv.io prouve.** Le lot fin est construit comme « part normale = v2 à 0,5 % près, plus des
dérives placées » (Lisez-moi du lot 4, fluides). Sur 35 séries × 12 mois, aucun mois hors dérive ne dépasse 0,1 %
d'écart (mesuré). deriv.io prouve donc qu'il calcule juste l'écart, le date à quelques jours et le chiffre exactement.

**Ce qu'il ne prouve pas.** (1) Qu'il détecterait sans une référence qui est, ici, le contrefactuel exact : la v2 2025
est la réponse. Sans elle, le même moteur fait 17 % de pertinence (expérience « sans référence » de deriv.io).
(2) Qu'il voit les dérives déjà dans la référence : trois sont trouvées dans la partie 4 (COP de S09, ventilation de S26,
gaz de S22). (3) Sa sobriété sur un parc réel, où aucun mois ne retombe à 0,5 % près sur un modèle. Le « 100 % » est
une mesure de justesse du chiffrage, pas de capacité de détection.

---

## 2. Les deux dérives manquées par Ergonia

**S31 électricité (+7 %, rampe d'octobre à décembre).** Mesuré sur les sorties d'Ergonia : son attendu surestime le
début de la saison de glace (septembre −10,5 %, octobre −4,4 %, novembre −5,8 %), parce que le niveau historique du
même mois est plus haut qu'en 2025. Un épisode à la baisse s'ouvre fin septembre et **gèle la référence** (règle
« référence gelée au début d'un épisode », baisse acceptée seulement après 60 jours). La rampe de +1,5 à +9 % reste
sous ce biais ; l'épisode CUSUM rouvert en décembre (+7,7 %) est ensuite écarté par le filtre de sobriété à 10 %.

**S26 gaz (+17 %, depuis fin septembre).** La dérive démarre avec la reprise de chauffe. La comparaison entre pairs
retire de l'attendu la médiane des écarts des autres compteurs de chauffage, lissée sur 7 jours ; à la reprise, tous
s'écartent ensemble, et la part propre à S26 est absorbée (Ergonia le dit dans son README).

**Règles testées sans la v2 2025** (seuils écrits avant lancement, `q2_regle.py`, `q2_regle_saison.py`) :

| Règle | Principe | Retrouve | Délai | Fausses alertes ajoutées |
|---|---|---|---|---|
| R1 — clôture mensuelle relative aux pairs | gaz / CAD / chaleur PAC, attendu *sans* correction des pairs ; écart du mois moins médiane des pairs ≥ 10 % deux mois de suite (seuils de la couche mensuelle figée d'Ergonia) | **S26 gaz** (+15 / +12 % vs pairs), et S37 (déjà trouvée) | 30.11, soit 61 j après le début de contrôle | **2** : S06 CAD (mai-juin, +24 / +27 %) et S32 gaz (juin-juillet, +20 / +15 %), toutes deux en été, à faible charge |
| R2 — rampe hebdomadaire | pente sur 8 semaines, t ≥ 3, 4 dernières semaines ≥ +5 % | **pas S31** (le biais de −10 % reste dessous) | — | 9 nouvelles (15 en tout) : **rejetée** |
| R3 — saison ancrée sur son premier mois | régime saisonnier déclaré (S31) : attendu(M) = mesuré de septembre × rapport médian v2(M)/v2(sept.) des saisons passées ; ≥ +5 % deux mois de suite | **S31** (oct. +8,8 %, nov. +7,3 %, déc. +16,6 %) | 30.11, soit 29 j après le début de contrôle (59 j après le 2 oct.) | 1 sur 3 saisons passées rejouées (décembre 2023, +11 / +7 %), 0 en 2025 |

Recommandation : R1 + R3 récupèrent les deux dérives pour **3 fausses alertes de plus** (2 en 2025, 1 historique). Les
deux fausses alertes de R1 tombent en été ; un plancher de charge les retirerait probablement, mais ce serait un
réglage fait après avoir vu le résultat : **non testé, à présenter comme piste de version 1.1**, pas comme acquis.

---

## 3. Écarts entre les deux projets, série par série

| Point | Chiffre retenu | Pourquoi | Incertitude |
|---|---|---|---|
| **S01 électricité** : 14 487 (deriv.io) contre 11 016 kWh (Ergonia) | **14 281 à 14 487 kWh** (mesuré) | 14 487 = somme lot − v2 d'avril à décembre (avril +206 kWh). Le chiffrage *de contrôle* d'Ergonia, sur sa propre période (2 mai → 31 décembre), donne 14 281 kWh. Les 11 016 kWh viennent de l'attendu du moteur autonome, qui porte le biais de niveau historique (12,4 % contre 16,8 % réels) : c'est une sous-estimation, pas un désaccord de fond. | ±0,5 % de bruit annoncé sur la part normale (mesuré : < 0,01 % hors dérive) ; date de début ±3 j ≈ ±180 kWh, déjà comprise dans la fourchette |
| **S26, injection d'août** : dérive ou défaut de registre | **Défaut de comptage du registre d'injection**, avec enjeu financier | Mesuré du 4 au 24 août : injection = 0 tous les quarts d'heure, production normale (85 kW à midi), soutirage nul. La « consommation » reconstituée (soutirage + production − injection) vaudrait 85 kW à midi contre 3,5 kW les semaines voisines, et épouse exactement la courbe solaire (corrélation 1,000) ; la nuit reste à 4 kW. Aucun stockage déclaré (feuille Installations). Une charge qui suit le soleil à la minute dans un centre sportif fermé en août n'est pas physique : l'énergie est partie au réseau sans être comptée. | 14 240 kWh (part injectée des 3 semaines voisines × production) à 14 750 kWh (lot − v2) non comptés ; 630 à 1 060 CHF à réclamer au distributeur (prix 2026, voir partie 7) |
| **COP de S09** : rapport annuel ou moyenne mensuelle | **Rapport annuel : 3,01 en 2025 contre 4,19 en 2024** (mesuré, v2) | La performance d'une PAC se juge sur l'énergie de l'année (Σ chaleur / Σ électricité). La moyenne des 12 COP mensuels (3,10 contre 4,30, chiffres de deriv.io) donne le même poids à un mois d'été qu'à janvier. deriv.io doit corriger ses deux chiffres de COP ; son excès (11 930 kWh, calculé mois par mois au COP du même mois 2024) reste juste. | Excès d'électricité 11 830 à 11 950 kWh selon la référence (4,18 sur 2021-24, 4,19 en 2024, 4,20 visé) ; 12 670 kWh avec la moyenne mensuelle, rejeté |
| **Facteur CO₂ de l'électricité** : 94 ou 125 g/kWh | **125 g CO₂-éq/kWh** (ACV) | Source primaire lue : liste KBOB/ecobau 2022, version 9.0 (`Ökobilanzdaten_im_Baubereich_V9.0.xlsx`, kbob.admin.ch), feuille Énergie, ligne 45.020 « CH-Verbrauchermix / Mix consommateur CH » : 0,125 kg CO₂-éq/kWh. Le canton de Vaud (fiche méthodologique du 15.12.2025) cite la même valeur depuis la version 6.2. **94 g/kWh n'apparaît sur aucune ligne électricité de KBOB** ni dans les documents du hackathon (Lisez-moi, guide, défis, decks) ; Ergonia l'attribue au « cahier des charges » sans référence retrouvée. | 125 g est un facteur moyen national non daté 2025 (Vaud : « pas mis à jour depuis 2018 ») ; pour mémoire, mix de production CH = 32 g (ligne 45.019). Ne jamais l'additionner au CO₂ direct |

---

## 4. Le reste du parc

**S22 gaz (trouvée par la couche mensuelle d'Ergonia) : confirmée, avec un début plus précoce.** Méthode indépendante :
kWh par DJ par saison de chauffe (mesuré) : 60,8 (2021-22) et 55,9 (2022-23, hiver de sobriété), puis 74,4 (2023-24)
et 75,3 (2024-25), soit +27 à +29 %. Écart mensuel à la signature 2021-2023 (estimé) : −3 à −7 % jusqu'en avril 2023,
puis **+10 % en mai, +20 % en juin, +26 % en août 2023** : la dérive commence au printemps 2023, pas en octobre
(Ergonia l'envisageait). La base d'été double (juillet + août : 1 458 kWh en 2023, 1 797 en 2024 et 2025) et la pente
monte de 56 à 69 kWh/DJ : un talon permanent (eau chaude, pertes de chaudière, circulateur) plus une perte de
rendement. L'électricité et l'eau de S22 sont stables (+1 %) : **pas de changement d'occupation** (indice contre).
Excès 2025 : 2 970 à 3 580 m³ (Ergonia : 3 514). Écart retombé à +17 % en novembre-décembre 2025.

**Dérives déjà dans la référence (invisibles au rapprochement de deriv.io)** :

- **Ventilation de S26 (sous-compteur) : +50 % depuis février 2024** (mesuré : janvier 2024 au niveau de 2023, février
  à +49 %, puis tous les mois +40 à +60 %). Indices contre : le gaz de S26 par DJ n'a pas monté (161 à 173 kWh/DJ,
  2023-26), donc « plus d'air neuf » n'est pas étayé ; et le reste du site a **baissé** de ~3 000 kWh/an quand la
  ventilation montait de ~8 500 kWh. Une partie peut être un recâblage du sous-compteur. Excès réel retenu : de la
  hausse du compteur général (6 850 kWh en 2025) à celle du sous-compteur (9 850 kWh). Causes restantes : horloge ou
  vitesse de ventilateur (régime nuit perdu), à confirmer sur place.
- **Eau de S26 en juin 2025 : pas une dérive.** Juin est le pic de chaque année (461, 510, 416, 442 m³ de 2021 à 2024) ;
  juin 2025 (425 m³) est dans la plage. Seul septembre 2025 (+10 %) dépasse légèrement : sous tout seuil raisonnable.
- **Pompes à chaleur** : COP annuel de S12 stable (4,48-4,49) ; S09 seule chute en 2025. Sans compteur de chaleur,
  l'électricité par DJ est stable pour S17 (4,4-4,6), S43 (11,6-12,3) et S04 (32,2-32,3, deux saisons) ; S18 et S28 ont
  moins de deux saisons : non jugeables.
- **Balayage de toutes les séries générales** (seuil de 15 % contre 2021-2023, fixé avant) : les autres écarts ont une
  explication déclarée (PAC de S04 en 2022 et S28 en 2024, PV de S07 en 2023, bornes de S47, LED de S48) ou sont
  ponctuels (eau de S23 et S35 en 2024 seulement). **À expliquer : S38 gaz −38 % depuis 2023-24**, sans événement
  déclaré (baisse : économie, changement d'usage ou compteur ; pas un coût).

---

## 5. Plafonnement de l'injection de S32

Mesuré : c'est l'**injection** qui est figée à 10,000 kWh par quart d'heure (40 kW), pas la production. La production
vaut alors injection plafonnée + consommation du site ; l'onduleur bride l'export.

- **Dates** : premier quart d'heure plafonné le 19 mai 2025 à 11 h 15, dernier le 30 septembre à 16 h 00.
- **Jours touchés** : 122 jours sur 135 (les 13 autres sont couverts) ; 4 001 quarts d'heure (~1 000 h). Mai 10 jours,
  juin 29, juillet 31, août 28, septembre 24. Trois quarts d'heure isolés hors épisode (13 mars, 11 décembre) touchent
  10,000 par hasard.
- **kWh perdus** : écart mesuré (lot − v2) de 43 248 kWh de production, **identique au kWh près à la perte d'injection** ;
  l'autoconsommation de midi est inchangée (22 kW avant, 21 kW pendant) et le soutirage n'en profite pas.
- **Le plafond explique-t-il tout ?** Production non bridée estimée par le toit sain de S26 × rapport S32/S26 appris hors
  épisode : 35 200 à 42 600 kWh perdus sur les quarts d'heure plafonnés selon le mois d'apprentissage (rapport 1,25 en
  avril ou octobre, 1,35 début mai), et seulement −1 000 à +1 000 kWh sur les quarts d'heure non plafonnés. **Le plafond
  explique 82 à 99 % de la perte** ; le reste tient dans l'incertitude du rapport entre toits (qui varie de 1,15 à 1,43
  d'un mois à l'autre), sans indice d'une seconde cause (pas d'écart hors plafond).

---

## 6. Causes : indices pour et contre

| Dérive | Cause retenue | Indice qui la soutient (mesuré) | Indice contraire cherché | Verdict |
|---|---|---|---|---|
| S01 électricité | équipement resté en marche permanente | excès de +2,4 kW la nuit, +2,9 kW en jour ouvré, +2,2 kW en jour fermé (profil corrigé de la saison) | excès limité aux heures ouvrées : absent | **étayée** |
| S30 électricité | régime réduit de nuit perdu (ventilation-déshumidification, filtration) | excès de +9,5 à +12,3 kW entre 0 et 5 h, nul le jour | Ergonia classe « hausse en occupation » / « talon permanent » : **contredit** par le profil | **étayée**, cause d'Ergonia écartée |
| S31 électricité | groupe froid qui se dégrade | excès qui triple d'octobre à décembre alors qu'il fait plus froid dehors (charge frigorifique en baisse) | excès surtout de jour (+13 à +25 kW) plus que de nuit (+3 à +7 kW) : compatible avec un rendement dégradé (excès ∝ charge), moins avec une panne fixe | **plausible** |
| S32 électricité | dérive lente et continue | écart mensuel qui croît chaque mois de mars à décembre | lien avec le plafond PV : **écarté** (la rampe commence avant et continue après) | cause **non identifiée** |
| S13 électricité | usage ajouté aux heures d'occupation | excès +0,9 kW en jour ouvré, +0,1 kW la nuit et les jours fermés | « appoint électrique » : le gaz de S13 reste exactement sur la v2 (aucune baisse, alors qu'un appoint de ~200 kWh/mois devrait en effacer ~2 %) | usage ajouté **étayé** ; appoint **affaibli** |
| S05 électricité | programme « vacances » non appliqué | jours ouvrés de vacances à 5,9-8,1 kW contre 2-2,5 kW les jours fermés et 16 kW en période scolaire ; nuits normales | — | **étayée** |
| S05 eau | écoulement permanent (fuite, chasse, remplissage, arrosage) | 3,8 m³/j les jours fermés de juillet contre 0,5 en juin et septembre ; ouvrés ≈ fermés | même cause que l'électricité ? **Non** : l'électricité ne monte que les jours ouvrés, l'eau tous les jours ; dates différentes (28.06 / 07.07) | **étayée, cause distincte** de S05 électricité ; fuite nocturne invisible au pas journalier |
| S26 gaz | régulation ou rendement (excès proportionnel au froid) | excès +2,7 % les jours doux, +18 % de 4 à 30 DJ, régression excès = 0,7 + 2,8 × DJ (r = 0,72) ; jours fermés = ouvrés | eau chaude ou fuite (excès constant) : **écartée** ; ventilation en air neuf : électricité et ventilation de S26 sur la v2 en 2025 | **étayée** (courbe de chauffe ou encrassement) |
| S37 CAD | courbe de chauffe relevée, réduit de nuit perdu | à 4-10 °C dehors : aller 72,5 → 78,7 °C, débit 2,8 → 4,2 m³/h, rapport énergie nuit/jour 0,77 → 0,92 | « avant » court (9 jours d'octobre) : ordre de grandeur, pas une mesure fine | **étayée** |
| S06 CAD | débit excessif (vanne bloquée ouverte, by-pass) | retour 48,7 → 57,4 °C, ΔT 23,3 → 17,0 K, débit 2,4 → 5,1 m³/h ; énergie mensuelle inchangée (lot = v2) | — | **étayée** ; aucun surcoût d'énergie facturée |
| S09 COP | perte de performance de la PAC | COP inférieur à 2024 *tous* les mois (2,97 à 3,26 contre 4,11 à 4,53) ; chaleur produite du lot = v2 | hausse de la demande de chaleur : n'explique pas un COP plus bas | **étayée** (sondes, échangeurs, fluide, appoint) |
| S32 PV | limitation d'injection de l'onduleur à 40 kW | injection figée à 10,000 kWh/qh pendant 122 jours | panneaux ou ombrage : pas d'écart hors plafond | **étayée** |
| S22 gaz | talon permanent + perte de rendement | base d'été +23 %, pente +23 % | changement d'occupation : électricité et eau stables | **plausible** (historique mensuel seul) |

Causes écartées faute d'appui : chauffage d'appoint électrique de S13 (affaibli), air neuf à S26 (gaz stable), lien
S32 électricité / plafond PV, cause commune S05 eau et électricité, « hausse en occupation » de S30.

---

## 7. Montants en fourchette et sources des prix

| Prix | Valeur | Source | Année |
|---|---|---|---|
| Électricité | 0,27 CHF/kWh tout compris | tarif fictif SIR, Lisez-moi des lots 4 | 2025 (convention du jeu) |
| Gaz | 9,61 à 10,31 ct/kWh PCS TTC (énergie + taxe CO₂ 2,158 ct + TVA 8,1 %, produits hors Vitale Vert) | SIG, Tarif gaz standard, `precedents_tarifs_gaz_naturel.pdf` | **en vigueur au 1.10.2025** ; le tarif de janvier à septembre 2025 n'a pas été lu (S22) |
| CAD | 8,19 à 11,61 ct/kWh TTC (GeniTerre Transition à Vertua Plus, part variable + contribution environnementale ; Vertua 9,77 ct) | SIG, `tarifs_thermique_2025.pdf` | 2025 |
| Eau | 1,50 à 2,80 CHF/m³, hors épuration | ge.ch, « coût de l'eau potable » | **non daté** |
| Injection PV | 4,40 ct HT (énergie seule) à 7,20 ct HT (avec GO), ≥ 100 kW avec consommation propre | SIG, C 2.8 « Rétributions… photovoltaïques » | **2026** (nouvelle teneur 1.1.2026) ; grille 2025 non trouvée |
| CO₂ gaz | 2,086 kg/m³ (direct) | Ref_CO2 du jeu (convention, OFEV) | convention fixe 2021-2025 |
| CO₂ électricité | 125 g CO₂-éq/kWh (ACV) | KBOB 2022 v9.0, ligne 45.020 | facteur non daté 2025 |

Rive-Claire est fictive : les prix genevois sont des ordres de grandeur réels appliqués à une commune fictive.
Les prix et facteurs qui ne correspondent pas à 2025 sont signalés en gras ci-dessus.

---

## Tableau unique des dérives retenues

Confiance : **élevée** = écart mesuré face à la v2 ou mesure physique directe, cause étayée par un second indice ;
**moyenne** = écart mesuré, cause plausible ; **faible** = historique mensuel seul.

| Site | Fluide | Depuis quand | Combien | CHF (fourchette) | Confiance | Cause probable | Contrôle sur place |
|---|---|---|---|---|---|---|---|
| S31 Patinoire | électricité | 2 oct. 2025, rampe, en cours | 17 380–19 610 kWh ; 2,2–2,5 t CO₂ (ACV) | 4 690–5 300 | moyenne | groupe froid qui se dégrade | condenseur, charge en fluide, consigne de glace, dégivrage ; intensités par départ |
| S30 Piscine | électricité | 4-5 juin 2025, en cours | 16 230–20 400 kWh (+5,8 %) ; 2,0–2,5 t | 4 380–5 510 | élevée | régime de nuit perdu | horloge ventilation-déshumidification, vitesse de filtration la nuit |
| S22 Salle communale | gaz | mai-juin 2023, en cours | 2025 seul : 2 970–3 580 m³ ; 6,2–7,5 t CO₂ direct | 3 190–4 120 | faible | talon permanent + perte de rendement | chaudière (rendement, réglage), circulateur et eau chaude en été |
| S37 Bois-Joli 23 | CAD | 3 nov. 2025 (18 nov. selon Ergonia), en cours | 36 080–36 140 kWh (+18 %) | 2 960–4 200 | élevée | courbe de chauffe relevée, réduit de nuit perdu | courbe et consignes, réduit nuit / week-end, vannes en manuel |
| S01 Mairie | électricité | 30 avril 2025, en cours | 14 280–14 490 kWh (+17 %) ; 1,8 t | 3 860–3 910 | élevée | charge permanente ~2,5 kW ajoutée | ronde bâtiment fermé : ventilation, climatisation serveurs, commutateurs manuel/auto |
| S09 Champ-Fleuri | électricité de la PAC | janv. 2025 (dans la référence), en cours | 11 830–11 950 kWh ; COP 3,01 contre 4,19 ; 1,5 t | 3 190–3 230 | élevée | perte de performance de la PAC | pression et débit des sondes, échangeurs, fluide frigorigène, appoint électrique |
| S26 Centre sportif | gaz | 16 oct. 2025 (30 sept. selon Ergonia), en cours | 2 315 m³ (25 740 kWh PCS, +18 %) ; 4,8 t CO₂ direct | 2 470–2 650 | élevée | régulation ou rendement de chaudière | courbe de chauffe, encrassement, combustion |
| S26 Centre sportif | électricité (ventilation) | févr. 2024 (dans la référence), en cours | 2025 : 6 850–9 850 kWh ; 0,9–1,2 t | 1 850–2 660 | moyenne | horaire ou vitesse de ventilation ; recâblage du sous-compteur possible | horloge et vitesse des ventilateurs ; schéma du sous-compteur |
| S32 Voirie | PV (injection) | 19 mai → 30 sept. 2025, terminée | 43 230–43 250 kWh non injectés | 1 900–3 110 | élevée | limitation d'injection à 40 kW | réglage de l'onduleur, consigne du distributeur ; ne pas réactiver le bridage |
| S32 Voirie | électricité | 28 mars 2025, rampe, en cours | 3 820–4 210 kWh ; 0,5 t | 1 030–1 140 | moyenne | non identifiée (lente, continue) | bornes de recharge, compresseur, chauffage d'atelier, rubans hors gel |
| S05 École des Crêts | électricité | 28 juin → 24 août 2025, terminée | 1 860–1 970 kWh | 500–530 | élevée | programme vacances non appliqué | programme horaire, locations d'été |
| S05 École des Crêts | eau | 7 juil. → 29 août 2025, terminée | 123 m³ (~105 l/h en continu) | 180–340 | élevée | écoulement permanent | index à la fermeture, chasses, arrosage, remplissage du chauffage |
| S13 Crèche du Centre | électricité | 17 nov. 2025, en cours | 490–505 kWh (+20 %) | 130–140 | moyenne | usage ajouté aux heures d'occupation | cuisine, ventilation, horloges ; appoint électrique peu probable (gaz inchangé) |
| S06 École de Bois-Joli | CAD (hydraulique) | 20 oct. 2025, en cours | retour +9 K, débit ×2, énergie inchangée | non chiffré | élevée | vanne primaire ouverte ou by-pass | vanne de régulation, échangeur, sonde de retour ; prévenir le réseau |
| S26 Centre sportif | injection (registre) | 4 → 24 août 2025, terminé | 14 240–14 750 kWh non comptés | 630–1 060 à réclamer | élevée | défaut de comptage, pas une dérive d'énergie | relevé du registre 2.8.0 ; réclamation au distributeur |

**Total des dérives (hors registre S26) : 30 350 à 36 840 CHF**, dont 22 110 à 26 830 CHF visibles par le
rapprochement v2 et 8 240 à 10 010 CHF déjà dans la référence (S09, ventilation de S26, S22 en 2025).

---

## Désaccords restants entre les deux projets

1. **Ce que « détecter » veut dire.** deriv.io lit la réponse (v2 2025) et chiffre juste ; Ergonia détecte sans elle
   et se trompe 7 fois sur 18. Les deux chiffres ne se comparent pas : à présenter côte à côte, pas en concurrence.
2. **Délai médian d'Ergonia** (8 jours) : compte des délais négatifs. Proposé : 11 jours (manquées comptées infinies).
3. **Dates de début** : S13 (20 juin pour Ergonia, 17 novembre pour la v2), S37 (27 août / 3 novembre), S30
   (24 juillet et 21 octobre / 4 juin), S32 électricité (octobre / 28 mars), S26 gaz (30 septembre / 16 octobre),
   S31 (1er novembre / 2 octobre), S22 (octobre 2023 / mai-juin 2023).
4. **S26 injection** : dérive pour Ergonia, défaut de comptage pour deriv.io — l'analyse tranche pour le défaut de
   comptage, avec un enjeu financier.
5. **Prix** : Ergonia « non chiffré » hors électricité ; deriv.io chiffre gaz, CAD, eau, PV. Proposé : fourchettes
   sourcées de la partie 7, années signalées.
6. **CO₂ électricité** : 94 g (Ergonia, sans source retrouvée) contre 125 g (KBOB v9.0) — 125 retenu.
7. **COP** : moyenne mensuelle (deriv.io, 3,10 / 4,30) contre rapport annuel (Ergonia, 3,01 / 4,19) — annuel retenu.
8. **Causes de S30** : nuit (deriv.io, étayé) contre occupation / talon (Ergonia, contredit).
9. **Fausse alerte S09 électricité d'Ergonia** (oct.-déc., +33 %) : fausse face à la v2, mais l'électricité générale de
   S09 est à +16 % sur 2025 face à l'historique à cause de la PAC. C'est l'écho de la dérive de COP, déjà dans la
   référence : ni tout à fait fausse ni une dérive distincte.
10. **Montants** : S01 (11 016 / 14 487 kWh), S30 (deux épisodes d'Ergonia, 16 230 / 20 396 kWh) : les montants
    d'Ergonia sous-estiment ; ses chiffrages de contrôle sont proches de ceux de deriv.io.

---

## À verser dans le dépôt d'Ergonia pour le rendu

Sans toucher à un seul seuil (le moteur reste en 1.0.0) :

1. `docs/RECONCILIATION.md` : ce rapport (texte seul ; aucune sortie CSV ni donnée, pour respecter
   `tests/test_garde_fous.py`).
2. `config/tarifs.yaml` : `co2_cycle_de_vie.electricite_g_par_kwh: 125`, source « KBOB/ecobau 2022 v9.0, ligne
   45.020 CH-Verbrauchermix » ; prix gaz, CAD, eau, injection en fourchette avec source et année (aujourd'hui `null`),
   ou au minimum en commentaire si l'équipe garde la règle « prix du jeu seulement ».
3. `DATA_SOURCES.md` : corriger la ligne « 94 g/kWh, cahier des charges » ; ajouter le tableau des prix de la partie 7.
4. `METHODS.md` : S26 injection reclassée en défaut de comptage avec enjeu financier (preuve : consommation
   reconstituée qui suit le soleil, corrélation 1,000) ; début de S22 au printemps 2023 ; COP = rapport annuel (déjà
   le cas, le dire) ; cause de S30 « régime de nuit » d'après le profil.
5. `outputs/evaluation.md` (via `src/pipeline.py`) ou `docs/` : médiane du délai sans délais négatifs (11 j) et le
   tableau du rejeu en temps réel de deriv.io (partie 1).
6. `CHANGELOG.md` : entrée « 1.0.1 — documentation, aucun seuil modifié » ; R1 et R3 décrites comme **candidates
   de version 1.1, non activées**, conçues en connaissant les dérives manquées (3 fausses alertes ajoutées).
7. `README.md`, limites : ajouter les trois dérives déjà dans la référence (S09, S26 ventilation, S22) et S38 à
   expliquer.
