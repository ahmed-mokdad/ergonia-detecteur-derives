# Usage de l'IA (Charte Energ-IACK, art. 5 à 7)

| Outil | Modèle | Rôle | Ce qu'il a reçu |
|---|---|---|---|
| Claude Code (Anthropic) | Claude Fable 5.2 (`claude-fable-5-2`) | Écriture du code, des tests et de la documentation, sous la direction de l'équipe ; exécution des calculs sur le poste local | Le cahier des charges de l'équipe et les seuls jeux **ouverts** Rive-Claire (lots 1, 4, 5). Aucun lot à accès restreint n'a été ouvert. |

**Dans l'application** : aucun appel à un LLM dans cette version. Les textes affichés sont produits par des gabarits déterministes à partir des chiffres du moteur. Si un LLM est ajouté, il sera désactivé par défaut, ne recevra que des agrégats issus des données ouvertes, ne produira que du texte (jamais un chiffre), et ses appels seront journalisés dans `logs/llm_calls.jsonl` sans la clé.

**Statut des chiffres** : chaque chiffre affiché est soit *mesuré* (lu dans les données), soit *estimé* (calculé par le moteur avec des hypothèses visibles). Aucun chiffre n'est généré par IA.

**Vérifié à la main par l'équipe** : à compléter avant le rendu (relecture des alertes vitrines, des prix et des attributions).
