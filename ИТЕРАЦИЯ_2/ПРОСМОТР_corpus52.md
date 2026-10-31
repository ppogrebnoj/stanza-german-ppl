# Просмотр глазами: corpus52
Алгоритмы: **S5** — наши 14 правил (rule.py rank1, напрямую); **S1:d** — LCA по дереву зависимостей (subtitle2go); **S1** — LCA по дереву зависимостей (subtitle2go); **S4** — гибрид S1+S2
Параметры — лучшие на корпусе 52 (с вашими ограничениями Q3/Q4). Блоки разделены ` / `.
Внизу каждого примера — **ваша** разметка (эталон).

---

**[iter1-umfassen-heizung]** 18 слов · регистр: —
Meine Dienstleistungen umfassen nicht nur die Arbeit an Heizungsanlagen, sondern auch die komplette Installation von Wasser- und Abwassersystemen.

- `S5`: Meine Dienstleistungen / umfassen nicht nur die Arbeit / an Heizungsanlagen, sondern auch die / komplette Installation von Wasser- und Abwassersystemen.
- `S1:d`: Meine Dienstleistungen umfassen / nicht nur die Arbeit / an Heizungsanlagen, sondern auch / die komplette Installation / von Wasser- und Abwassersystemen.
- `S1`: Meine Dienstleistungen umfassen nicht nur / die Arbeit an Heizungsanlagen, / sondern auch die komplette Installation / von Wasser- und Abwassersystemen.
- `S4`: Meine Dienstleistungen umfassen / nicht nur die Arbeit / an Heizungsanlagen, sondern auch / die komplette Installation / von Wasser- und Abwassersystemen.
- `человек`: Meine Dienstleistungen umfassen / nicht nur die Arbeit an Heizungsanlagen, / sondern auch die komplette Installation / von Wasser- und Abwassersystemen.

**[iter3-c5-weil]** 7 слов · регистр: —
Ich weiß es, weil er müde ist.

- `S5`: Ich weiß / es, weil er müde ist.
- `S1:d`: Ich weiß es, / weil er müde ist.
- `S1`: Ich weiß es, / weil er müde ist.
- `S4`: Ich weiß es, / weil er müde ist.
- `человек`: Ich weiß es, / weil er müde ist.

**[iter3-c4-dann]** 5 слов · регистр: —
Er kam dann nach Hause.

- `S5`: Er kam dann nach Hause.
- `S1:d`: Er kam dann nach Hause.
- `S1`: Er kam dann / nach Hause.
- `S4`: Er kam dann / nach Hause.
- `человек`: Er kam dann nach Hause.

**[iter4-s1-geschaeftsidee]** 6 слов · регистр: —
Heute möchte ich meine Geschäftsidee vorstellen.

- `S5`: Heute möchte ich / meine Geschäftsidee vorstellen.
- `S1:d`: Heute möchte ich / meine Geschäftsidee vorstellen.
- `S1`: Heute möchte ich / meine Geschäftsidee vorstellen.
- `S4`: Heute möchte ich / meine Geschäftsidee vorstellen.
- `человек`: Heute möchte ich / meine Geschäftsidee vorstellen.

**[iter4-s2-sanitaer-trunc]** 13 слов · регистр: —
In meinem Heimatland habe ich als Selbstständiger im Bereich Sanitär- und Heizungstechnik gearbeitet.

- `S5`: In meinem Heimatland / habe ich als Selbstständiger / im Bereich Sanitär- und Heizungstechnik gearbeitet.
- `S1:d`: In meinem Heimatland / habe ich als Selbstständiger / im Bereich Sanitär- und Heizungstechnik gearbeitet.
- `S1`: In meinem Heimatland / habe ich als Selbstständiger / im Bereich Sanitär- und Heizungstechnik gearbeitet.
- `S4`: In meinem Heimatland / habe ich als Selbstständiger / im Bereich Sanitär- und Heizungstechnik gearbeitet.
- `человек`: In meinem Heimatland habe ich / als Selbstständiger im Bereich / Sanitär- und Heizungstechnik gearbeitet.

**[iter4-s3-heizungsanlagen]** 15 слов · регистр: —
Mein Service umfasst die Installation, Wartung und Reparatur von Heizungsanlagen wie Gas-, Elektro- und Holzkesseln.

- `S5`: Mein Service umfasst die Installation, / Wartung und Reparatur von Heizungsanlagen / wie Gas-, Elektro- und Holzkesseln.
- `S1:d`: Mein Service umfasst / die Installation, Wartung und Reparatur / von Heizungsanlagen wie Gas-, / Elektro- und Holzkesseln.
- `S1`: Mein Service umfasst / die Installation, Wartung / und Reparatur / von Heizungsanlagen wie Gas-, / Elektro- und Holzkesseln.
- `S4`: Mein Service umfasst / die Installation, Wartung und Reparatur / von Heizungsanlagen wie Gas-, / Elektro- und Holzkesseln.
- `человек`: Mein Service umfasst / die Installation, Wartung und Reparatur / von Heizungsanlagen wie Gas-, Elektro- und Holzkesseln.

**[iter4-s4-komplettservice]** 22 слов · регистр: —
Das Besondere an meinem Angebot ist der Komplettservice aus einer Hand, von der Planung und Neuinstallation bis zur regelmäßigen Wartung und Notfallreparatur.

- `S5`: Das Besondere an meinem Angebot ist / der Komplettservice aus einer Hand, von / der Planung und Neuinstallation bis zur / regelmäßigen Wartung und Notfallreparatur.
- `S1:d`: Das Besondere an meinem Angebot / ist der Komplettservice aus / einer Hand, von der Planung / und Neuinstallation bis zur / regelmäßigen Wartung und Notfallreparatur.
- `S1`: Das Besondere an meinem Angebot / ist der Komplettservice / aus einer Hand, / von der Planung und Neuinstallation / bis zur regelmäßigen Wartung / und Notfallreparatur.
- `S4`: Das Besondere an meinem Angebot / ist der Komplettservice / aus einer Hand, / von der Planung und Neuinstallation / bis zur regelmäßigen Wartung / und Notfallreparatur.
- `человек`: Das Besondere an meinem Angebot ist / der Komplettservice aus einer Hand, / von der Planung und Neuinstallation / bis zur regelmäßigen Wartung und Notfallreparatur.

**[iter4-s5-zielgruppe-cop]** 6 слов · регистр: —
Meine Zielgruppe sind Privatkunden und Hausverwaltungen.

- `S5`: Meine Zielgruppe sind / Privatkunden und Hausverwaltungen.
- `S1:d`: Meine Zielgruppe / sind Privatkunden und Hausverwaltungen.
- `S1`: Meine Zielgruppe / sind Privatkunden und Hausverwaltungen.
- `S4`: Meine Zielgruppe / sind Privatkunden und Hausverwaltungen.
- `человек`: Meine Zielgruppe sind / Privatkunden und Hausverwaltungen.

**[iter4-s6-dass-weil]** 18 слов · регистр: —
Ich denke, dass diese Idee sehr gute Chancen auf dem Markt hat, weil kompetente Handwerker immer gefragt sind.

- `S5`: Ich denke, dass / diese Idee sehr / gute Chancen auf / dem Markt hat, / weil kompetente Handwerker / immer gefragt sind.
- `S1:d`: Ich denke, dass diese Idee / sehr gute Chancen / auf dem Markt hat, / weil kompetente Handwerker / immer gefragt sind.
- `S1`: Ich denke, dass diese Idee / sehr gute Chancen / auf dem Markt hat, / weil kompetente Handwerker / immer gefragt sind.
- `S4`: Ich denke, dass diese Idee / sehr gute Chancen / auf dem Markt hat, / weil kompetente Handwerker / immer gefragt sind.
- `человек`: Ich denke, dass / diese Idee sehr gute Chancen / auf dem Markt hat, / weil kompetente Handwerker / immer gefragt sind.

**[iter4b-s3-asyndeton]** 15 слов · регистр: —
Mein Service umfasst die Installation, Wartung und Reparatur von Heizungsanlagen wie Gas-, Elektro- und Holzkesseln.

- `S5`: Mein Service umfasst die Installation, / Wartung und Reparatur von Heizungsanlagen / wie Gas-, Elektro- und Holzkesseln.
- `S1:d`: Mein Service umfasst / die Installation, Wartung und Reparatur / von Heizungsanlagen wie Gas-, / Elektro- und Holzkesseln.
- `S1`: Mein Service umfasst / die Installation, Wartung / und Reparatur / von Heizungsanlagen wie Gas-, / Elektro- und Holzkesseln.
- `S4`: Mein Service umfasst / die Installation, Wartung und Reparatur / von Heizungsanlagen wie Gas-, / Elektro- und Holzkesseln.
- `человек`: Mein Service umfasst die Installation, / Wartung und Reparatur von Heizungsanlagen / wie Gas-, Elektro- und Holzkesseln.

**[iter4b-s6-weil-block]** 18 слов · регистр: —
Ich denke, dass diese Idee sehr gute Chancen auf dem Markt hat, weil kompetente Handwerker immer gefragt sind.

- `S5`: Ich denke, dass / diese Idee sehr / gute Chancen auf / dem Markt hat, / weil kompetente Handwerker / immer gefragt sind.
- `S1:d`: Ich denke, dass diese Idee / sehr gute Chancen / auf dem Markt hat, / weil kompetente Handwerker / immer gefragt sind.
- `S1`: Ich denke, dass diese Idee / sehr gute Chancen / auf dem Markt hat, / weil kompetente Handwerker / immer gefragt sind.
- `S4`: Ich denke, dass diese Idee / sehr gute Chancen / auf dem Markt hat, / weil kompetente Handwerker / immer gefragt sind.
- `человек`: Ich denke, dass / diese Idee sehr gute Chancen / auf dem Markt hat, / weil kompetente Handwerker immer gefragt sind.

**[iter5-s3-relativ]** 11 слов · регистр: —
Das ist ein Unternehmen, das Tresore und Sicherheitslösungen für Banken produziert.

- `S5`: Das ist ein Unternehmen, das Tresore / und Sicherheitslösungen für Banken produziert.
- `S1:d`: Das ist ein Unternehmen, / das Tresore und Sicherheitslösungen / für Banken produziert.
- `S1`: Das ist ein Unternehmen, / das Tresore und Sicherheitslösungen / für Banken produziert.
- `S4`: Das ist ein Unternehmen, / das Tresore und Sicherheitslösungen / für Banken produziert.
- `человек`: Das ist ein Unternehmen, / das Tresore und Sicherheitslösungen / für Banken produziert.

**[iter5-s9-genitiv]** 8 слов · регистр: —
Später habe ich als Leiter des Konstruktionsbüros gearbeitet.

- `S5`: Später habe ich / als Leiter des Konstruktionsbüros gearbeitet.
- `S1:d`: Später habe ich / als Leiter des Konstruktionsbüros gearbeitet.
- `S1`: Später habe ich / als Leiter des Konstruktionsbüros gearbeitet.
- `S4`: Später habe ich / als Leiter des Konstruktionsbüros gearbeitet.
- `человек`: Später habe ich als Leiter / des Konstruktionsbüros gearbeitet.

**[iter5-s12-direktor]** 9 слов · регистр: —
Schließlich habe ich die Position des Technischen Direktors übernommen.

- `S5`: Schließlich habe ich / die Position des / Technischen Direktors übernommen.
- `S1:d`: Schließlich habe ich die Position / des Technischen Direktors übernommen.
- `S1`: Schließlich habe ich / die Position / des Technischen Direktors übernommen.
- `S4`: Schließlich habe ich / die Position / des Technischen Direktors übernommen.
- `человек`: Schließlich habe ich die Position / des Technischen Direktors übernommen.

**[iter5-s13-conj-det]** 19 слов · регистр: —
In dieser Rolle war ich für die gesamte technische Strategie, die Optimierung der Produktionsprozesse und die strategische Planung verantwortlich.

- `S5`: In dieser Rolle / war ich für die gesamte / technische Strategie, die Optimierung der Produktionsprozesse / und die strategische Planung verantwortlich.
- `S1:d`: In dieser Rolle war ich / für die gesamte technische Strategie, / die Optimierung der Produktionsprozesse / und die strategische Planung verantwortlich.
- `S1`: In dieser Rolle war ich / für die gesamte technische Strategie, / die Optimierung der Produktionsprozesse / und die strategische Planung verantwortlich.
- `S4`: In dieser Rolle war ich / für die gesamte technische Strategie, / die Optimierung der Produktionsprozesse / und die strategische Planung verantwortlich.
- `человек`: In dieser Rolle war ich / für die gesamte technische Strategie, / die Optimierung der Produktionsprozesse / und die strategische Planung verantwortlich.

**[iter5-s5-propn-adv]** 19 слов · регистр: —
Das Unternehmen hat Standorte in der Ukraine sowie in Polen und exportiert seine Produkte in mehr als fünfundfünfzig Länder.

- `S5`: Das Unternehmen hat / Standorte in der Ukraine sowie / in Polen und / exportiert seine Produkte / in mehr als fünfundfünfzig Länder.
- `S1:d`: Das Unternehmen hat Standorte / in der Ukraine / sowie in Polen / und exportiert seine Produkte / in mehr als fünfundfünfzig Länder.
- `S1`: Das Unternehmen hat Standorte / in der Ukraine / sowie in Polen / und exportiert seine Produkte / in mehr als fünfundfünfzig Länder.
- `S4`: Das Unternehmen hat Standorte / in der Ukraine / sowie in Polen / und exportiert seine Produkte / in mehr als fünfundfünfzig Länder.
- `человек`: Das Unternehmen hat Standorte / in der Ukraine / sowie in Polen / und exportiert seine Produkte / in mehr als fünfundfünfzig Länder.

**[iter5b-s2-bei-der-firma]** 7 слов · регистр: —
Ich habe bei der Firma „Paritet-K“ gearbeitet.

- `S5`: Ich habe / bei der Firma „Paritet-K“ gearbeitet.
- `S1:d`: Ich habe / bei der Firma „Paritet-K“ gearbeitet.
- `S1`: Ich habe / bei der Firma „Paritet-K“ gearbeitet.
- `S4`: Ich habe / bei der Firma „Paritet-K“ gearbeitet.
- `человек`: Ich habe bei / der Firma „Paritet-K“ gearbeitet.

**[iter6-min2-fuer-mich-ist]** 8 слов · регистр: —
Für mich ist eine gute Arbeitsatmosphäre sehr wichtig.

- `S5`: Für mich ist / eine gute Arbeitsatmosphäre sehr wichtig.
- `S1:d`: Für mich ist / eine gute Arbeitsatmosphäre sehr wichtig.
- `S1`: Für mich ist / eine gute Arbeitsatmosphäre sehr wichtig.
- `S4`: Für mich ist / eine gute Arbeitsatmosphäre / sehr wichtig.
- `человек`: Für mich ist / eine gute Arbeitsatmosphäre / sehr wichtig.

**[iter6-min2-taegliche-motivation]** 5 слов · регистр: —
Sie gibt mir tägliche Motivation.

- `S5`: Sie gibt mir tägliche Motivation.
- `S1:d`: Sie gibt mir tägliche Motivation.
- `S1`: Sie gibt mir / tägliche Motivation.
- `S4`: Sie gibt mir / tägliche Motivation.
- `человек`: Sie gibt mir / tägliche Motivation.

**[iter6-min2-erstens-ist]** 4 слов · регистр: —
Erstens ist Jobsicherheit wichtig.

- `S5`: Erstens ist Jobsicherheit wichtig.
- `S1:d`: Erstens ist Jobsicherheit wichtig.
- `S1`: Erstens ist Jobsicherheit wichtig.
- `S4`: Erstens ist Jobsicherheit wichtig.
- `человек`: Erstens ist / Jobsicherheit wichtig.

**[iter6-min2-gibt-vertrauen]** 5 слов · регистр: —
Ein stabiler Job gibt Vertrauen.

- `S5`: Ein stabiler Job gibt Vertrauen.
- `S1:d`: Ein stabiler Job gibt Vertrauen.
- `S1`: Ein stabiler Job gibt Vertrauen.
- `S4`: Ein stabiler Job / gibt Vertrauen.
- `человек`: Ein stabiler Job / gibt Vertrauen.

**[iter6-min2-drittens-ist]** 6 слов · регистр: —
Drittens ist eine offene Kommunikation wichtig.

- `S5`: Drittens ist eine / offene Kommunikation wichtig.
- `S1:d`: Drittens ist / eine offene Kommunikation wichtig.
- `S1`: Drittens ist / eine offene Kommunikation wichtig.
- `S4`: Drittens ist / eine offene Kommunikation wichtig.
- `человек`: Drittens ist / eine offene Kommunikation wichtig.

**[iter6-min2-gute-kollegen]** 5 слов · регистр: —
Gute Kollegen unterstützen sich gegenseitig.

- `S5`: Gute Kollegen unterstützen sich gegenseitig.
- `S1:d`: Gute Kollegen unterstützen sich gegenseitig.
- `S1`: Gute Kollegen unterstützen sich gegenseitig.
- `S4`: Gute Kollegen / unterstützen sich gegenseitig.
- `человек`: Gute Kollegen / unterstützen sich gegenseitig.

**[iter6-min2-arbeitsklima-muss]** 5 слов · регистр: —
Das Arbeitsklima muss respektvoll sein.

- `S5`: Das Arbeitsklima muss respektvoll sein.
- `S1:d`: Das Arbeitsklima muss respektvoll sein.
- `S1`: Das Arbeitsklima / muss respektvoll sein.
- `S4`: Das Arbeitsklima / muss respektvoll sein.
- `человек`: Das Arbeitsklima / muss respektvoll sein.

**[iter6-min2-gute-kommunikation-war]** 6 слов · регистр: —
Gute Kommunikation war mir sehr wichtig.

- `S5`: Gute Kommunikation war / mir sehr wichtig.
- `S1:d`: Gute Kommunikation / war mir sehr wichtig.
- `S1`: Gute Kommunikation / war mir sehr wichtig.
- `S4`: Gute Kommunikation / war mir sehr wichtig.
- `человек`: Gute Kommunikation / war mir sehr wichtig.

**[iter6-min2-selbststaendiger-klimaanlagen]** 9 слов · регистр: —
Nach der Arbeit habe ich als Selbstständiger Klimaanlagen installiert.

- `S5`: Nach der Arbeit / habe ich als Selbstständiger Klimaanlagen installiert.
- `S1:d`: Nach der Arbeit habe ich / als Selbstständiger Klimaanlagen installiert.
- `S1`: Nach der Arbeit habe ich / als Selbstständiger Klimaanlagen installiert.
- `S4`: Nach der Arbeit habe ich / als Selbstständiger Klimaanlagen installiert.
- `человек`: Nach der Arbeit habe ich / als Selbstständiger / Klimaanlagen installiert.

**[iter6-min2-heizungsanlagen-eingebaut]** 6 слов · регистр: —
Im Winter habe ich Heizungsanlagen eingebaut.

- `S5`: Im Winter habe ich / Heizungsanlagen eingebaut.
- `S1:d`: Im Winter / habe ich Heizungsanlagen eingebaut.
- `S1`: Im Winter / habe ich Heizungsanlagen eingebaut.
- `S4`: Im Winter / habe ich Heizungsanlagen eingebaut.
- `человек`: Im Winter habe ich / Heizungsanlagen eingebaut.

**[iter7-c12-als-technischer]** 6 слов · регистр: —
Ich habe als Technischer Direktor gearbeitet.

- `S5`: Ich habe als / Technischer Direktor gearbeitet.
- `S1:d`: Ich habe / als Technischer Direktor gearbeitet.
- `S1`: Ich habe / als Technischer Direktor gearbeitet.
- `S4`: Ich habe / als Technischer Direktor gearbeitet.
- `человек`: Ich habe als / Technischer Direktor gearbeitet.

**[iter7-c12-neue-dinge]** 9 слов · регистр: —
Wenn man neue Dinge lernen kann, bleibt man motiviert.

- `S5`: Wenn man neue Dinge lernen kann, / bleibt man motiviert.
- `S1:d`: Wenn man neue Dinge / lernen kann, bleibt man motiviert.
- `S1`: Wenn man / neue Dinge lernen kann, / bleibt man motiviert.
- `S4`: Wenn man / neue Dinge lernen kann, / bleibt man motiviert.
- `человек`: Wenn man / neue Dinge lernen kann, / bleibt man motiviert.

**[iter7-c12-wichtigen-menschen]** 9 слов · регистр: —
Ich möchte von einem für mich wichtigen Menschen erzählen.

- `S5`: Ich möchte von / einem für mich / wichtigen Menschen erzählen.
- `S1:d`: Ich möchte / von einem für mich wichtigen Menschen erzählen.
- `S1`: Ich möchte / von einem für mich / wichtigen Menschen erzählen.
- `S4`: Ich möchte / von einem für mich / wichtigen Menschen erzählen.
- `человек`: Ich möchte von / einem für mich / wichtigen Menschen erzählen.

**[iter7-c13-moeglichkeit-sich]** 13 слов · регистр: —
Die Möglichkeit, sich weiterzuentwickeln, ist wichtig, zum Beispiel durch Kurse oder neue Aufgaben.

- `S5`: Die Möglichkeit, sich weiterzuentwickeln, / ist wichtig, zum Beispiel durch / Kurse oder neue Aufgaben.
- `S1:d`: Die Möglichkeit, sich weiterzuentwickeln, / ist wichtig, / zum Beispiel durch Kurse / oder neue Aufgaben.
- `S1`: Die Möglichkeit, sich weiterzuentwickeln, / ist wichtig, / zum Beispiel durch Kurse / oder neue Aufgaben.
- `S4`: Die Möglichkeit, sich weiterzuentwickeln, / ist wichtig, / zum Beispiel durch Kurse / oder neue Aufgaben.
- `человек`: Die Möglichkeit, / sich weiterzuentwickeln, ist wichtig, / zum Beispiel durch Kurse / oder neue Aufgaben.

**[iter7-c13-gelernt-bin]** 13 слов · регистр: —
Mein Vater war Schweißer und ich habe auch Schweißer gelernt, bin aber Schweißingenieur.

- `S5`: Mein Vater / war Schweißer und ich habe / auch Schweißer gelernt, / bin aber Schweißingenieur.
- `S1:d`: Mein Vater war Schweißer / und ich habe auch / Schweißer gelernt, bin aber Schweißingenieur.
- `S1`: Mein Vater war Schweißer / und ich habe auch / Schweißer gelernt, bin aber Schweißingenieur.
- `S4`: Mein Vater war Schweißer / und ich habe / auch Schweißer gelernt, / bin aber Schweißingenieur.
- `человек`: Mein Vater war Schweißer / und ich habe auch Schweißer gelernt, / bin aber Schweißingenieur.

**[iter7-c13-getan-was]** 11 слов · регистр: —
Aber mein Vater hat alles für uns getan, was er konnte.

- `S5`: Aber mein Vater / hat alles für uns getan, / was er konnte.
- `S1:d`: Aber mein Vater hat / alles für uns getan, / was er konnte.
- `S1`: Aber mein Vater hat / alles für uns getan, / was er konnte.
- `S4`: Aber mein Vater hat / alles für uns getan, / was er konnte.
- `человек`: Aber mein Vater hat / alles für uns getan, / was er konnte.

**[iter7-c13-ich-glaube-er]** 9 слов · регистр: —
Ich glaube, er hätte mir noch viel zeigen können.

- `S5`: Ich glaube, er hätte mir / noch viel zeigen können.
- `S1:d`: Ich glaube, er hätte / mir noch viel zeigen können.
- `S1`: Ich glaube, / er hätte mir / noch viel zeigen können.
- `S4`: Ich glaube, er hätte / mir noch viel zeigen können.
- `человек`: Ich glaube, / er hätte mir / noch viel zeigen können.

**[iter7-seg2-erhat-meine-einstellung]** 8 слов · регистр: —
Er hat meine Einstellung zur Arbeit stark beeinflusst.

- `S5`: Er hat / meine Einstellung zur Arbeit stark beeinflusst.
- `S1:d`: Er hat meine Einstellung / zur Arbeit stark beeinflusst.
- `S1`: Er hat meine Einstellung / zur Arbeit stark beeinflusst.
- `S4`: Er hat meine Einstellung / zur Arbeit stark beeinflusst.
- `человек`: Er hat / meine Einstellung zur Arbeit / stark beeinflusst.

**[iter8-s1-arbeitsuche-ukraine]** 9 слов · регистр: —
Ich möchte über die Arbeitssuche in der Ukraine erzählen.

- `S5`: Ich möchte über / die Arbeitssuche in / der Ukraine erzählen.
- `S1:d`: Ich möchte / über die Arbeitssuche in der Ukraine erzählen.
- `S1`: Ich möchte / über die Arbeitssuche / in der Ukraine erzählen.
- `S4`: Ich möchte / über die Arbeitssuche / in der Ukraine erzählen.
- `человек`: Ich möchte / über die Arbeitssuche / in der Ukraine erzählen.

**[iter8-s2-online]** 6 слов · регистр: —
Heute macht man fast alles online.

- `S5`: Heute macht man / fast alles online.
- `S1:d`: Heute macht man / fast alles online.
- `S1`: Heute macht man / fast alles online.
- `S4`: Heute macht man / fast alles online.
- `человек`: Heute macht man / fast alles online.

**[iter8-s3-jobportale]** 14 слов · регистр: —
Die meisten Jobs findet man auf Jobportalen wie Work.ua oder Rabota.ua und auf LinkedIn.

- `S5`: Die meisten Jobs / findet man auf Jobportalen wie Work.ua / oder Rabota.ua und auf LinkedIn.
- `S1:d`: Die meisten Jobs findet man / auf Jobportalen wie Work.ua / oder Rabota.ua und auf LinkedIn.
- `S1`: Die meisten Jobs findet man / auf Jobportalen wie Work.ua / oder Rabota.ua / und auf LinkedIn.
- `S4`: Die meisten Jobs findet man / auf Jobportalen wie Work.ua / oder Rabota.ua / und auf LinkedIn.
- `человек`: Die meisten Jobs / findet man auf Jobportalen / wie Work.ua oder Rabota.ua / und auf LinkedIn.

**[iter8-s4-tipps]** 7 слов · регистр: —
Tipps von Freunden sind auch sehr wichtig.

- `S5`: Tipps von Freunden / sind auch sehr wichtig.
- `S1:d`: Tipps von Freunden / sind auch sehr wichtig.
- `S1`: Tipps von Freunden / sind auch sehr wichtig.
- `S4`: Tipps von Freunden / sind auch sehr wichtig.
- `человек`: Tipps von Freunden sind / auch sehr wichtig.

**[iter8-s5-agenturen]** 8 слов · регистр: —
Es gibt auch private Agenturen für die Arbeitssuche.

- `S5`: Es gibt auch / private Agenturen für die Arbeitssuche.
- `S1:d`: Es gibt auch private / Agenturen für die Arbeitssuche.
- `S1`: Es gibt auch / private Agenturen für die Arbeitssuche.
- `S4`: Es gibt auch private Agenturen / für die Arbeitssuche.
- `человек`: Es gibt auch / private Agenturen / für die Arbeitssuche.

**[iter8-s6-kontakt]** 6 слов · регистр: —
Der erste Kontakt ist meistens online.

- `S5`: Der erste Kontakt / ist meistens online.
- `S1:d`: Der erste Kontakt / ist meistens online.
- `S1`: Der erste Kontakt / ist meistens online.
- `S4`: Der erste Kontakt / ist meistens online.
- `человек`: Der erste Kontakt ist / meistens online.

**[iter8-s7-lebenslauf]** 10 слов · регистр: —
Man schickt den Lebenslauf über ein Portal oder per E-Mail.

- `S5`: Man schickt den Lebenslauf über / ein Portal oder / per E-Mail.
- `S1:d`: Man schickt den Lebenslauf / über ein Portal / oder per E-Mail.
- `S1`: Man schickt den Lebenslauf / über ein Portal / oder per E-Mail.
- `S4`: Man schickt den Lebenslauf / über ein Portal / oder per E-Mail.
- `человек`: Man schickt den Lebenslauf / über ein Portal / oder per E-Mail.

**[iter8-s8-anschreiben]** 18 слов · регистр: —
Im Gegensatz zu Deutschland ist ein Anschreiben in der Ukraine oft sehr kurz oder wird gar nicht benötigt.

- `S5`: Im Gegensatz zu Deutschland ist ein / Anschreiben in der Ukraine oft / sehr kurz oder / wird gar nicht benötigt.
- `S1:d`: Im Gegensatz zu Deutschland / ist ein Anschreiben / in der Ukraine oft / sehr kurz oder wird / gar nicht benötigt.
- `S1`: Im Gegensatz zu Deutschland / ist ein Anschreiben / in der Ukraine oft / sehr kurz oder wird / gar nicht benötigt.
- `S4`: Im Gegensatz zu Deutschland / ist ein Anschreiben / in der Ukraine oft / sehr kurz oder wird / gar nicht benötigt.
- `человек`: Im Gegensatz zu Deutschland ist / ein Anschreiben in der Ukraine / oft sehr kurz / oder wird gar nicht benötigt.

**[iter8-s9-lebenslauf-wichtigst]** 7 слов · регистр: —
Das Wichtigste ist ein gut geschriebener Lebenslauf.

- `S5`: Das Wichtigste / ist ein gut geschriebener Lebenslauf.
- `S1:d`: Das Wichtigste ist / ein gut geschriebener Lebenslauf.
- `S1`: Das Wichtigste ist / ein gut geschriebener Lebenslauf.
- `S4`: Das Wichtigste ist / ein gut geschriebener Lebenslauf.
- `человек`: Das Wichtigste ist / ein gut geschriebener Lebenslauf.

**[iter8-s10-schritte]** 11 слов · регистр: —
Der Bewerbungsprozess besteht in der Regel aus zwei bis drei Schritten.

- `S5`: Der Bewerbungsprozess besteht / in der Regel / aus zwei bis drei Schritten.
- `S1:d`: Der Bewerbungsprozess besteht / in der Regel / aus zwei bis drei Schritten.
- `S1`: Der Bewerbungsprozess besteht / in der Regel / aus zwei bis drei Schritten.
- `S4`: Der Bewerbungsprozess besteht / in der Regel / aus zwei bis drei Schritten.
- `человек`: Der Bewerbungsprozess besteht / in der Regel / aus zwei bis drei Schritten.

**[iter8-s11-erstgespraech]** 10 слов · регистр: —
Zuerst gibt es ein kurzes Erstgespräch mit einem Personalleiter (Personalmanager).

- `S5`: Zuerst gibt / es ein kurzes Erstgespräch mit / einem Personalleiter (Personalmanager).
- `S1:d`: Zuerst gibt es / ein kurzes Erstgespräch / mit einem Personalleiter (Personalmanager).
- `S1`: Zuerst gibt es / ein kurzes Erstgespräch / mit einem Personalleiter (Personalmanager).
- `S4`: Zuerst gibt es / ein kurzes Erstgespräch / mit einem Personalleiter (Personalmanager).
- `человек`: Zuerst gibt es / ein kurzes Erstgespräch / mit einem Personalleiter (Personalmanager).

**[iter8-s12-vorstellungsgespraech]** 8 слов · регистр: —
Danach folgt ein fachliches Vorstellungsgespräch mit dem Abteilungsleiter.

- `S5`: Danach folgt ein / fachliches Vorstellungsgespräch mit dem Abteilungsleiter.
- `S1:d`: Danach folgt ein fachliches / Vorstellungsgespräch mit dem Abteilungsleiter.
- `S1`: Danach folgt / ein fachliches Vorstellungsgespräch / mit dem Abteilungsleiter.
- `S4`: Danach folgt / ein fachliches Vorstellungsgespräch / mit dem Abteilungsleiter.
- `человек`: Danach folgt / ein fachliches Vorstellungsgespräch / mit dem Abteilungsleiter.

**[iter8-s13-testaufgabe]** 15 слов · регистр: —
Anders als in Deutschland ist es oft auch notwendig, eine kleine Testaufgabe zu erledigen (lösen).

- `S5`: Anders als in Deutschland ist / es oft auch notwendig, eine / kleine Testaufgabe zu erledigen (lösen).
- `S1:d`: Anders als in Deutschland / ist es oft / auch notwendig, eine kleine / Testaufgabe zu erledigen (lösen).
- `S1`: Anders als in Deutschland ist / es oft auch notwendig, / eine kleine Testaufgabe / zu erledigen (lösen).
- `S4`: Anders als in Deutschland / ist es oft auch notwendig, / eine kleine Testaufgabe / zu erledigen (lösen).
- `человек`: Anders als in Deutschland ist es / oft auch notwendig, / eine kleine Testaufgabe zu erledigen (lösen).

**[iter8-s14a-sagen]** 4 слов · регистр: —
Zusammenfassend möchte ich sagen:

- `S5`: Zusammenfassend möchte ich sagen:
- `S1:d`: Zusammenfassend möchte ich sagen:
- `S1`: Zusammenfassend möchte ich sagen:
- `S4`: Zusammenfassend möchte ich sagen:
- `человек`: Zusammenfassend möchte ich sagen:

**[iter8-s14b-jobsuche]** 11 слов · регистр: —
Die Jobsuche in der Ukraine ist ein schneller und moderner Prozess.

- `S5`: Die Jobsuche in / der Ukraine ist / ein schneller und moderner Prozess.
- `S1:d`: Die Jobsuche in der Ukraine / ist ein schneller / und moderner Prozess.
- `S1`: Die Jobsuche in der Ukraine / ist ein schneller / und moderner Prozess.
- `S4`: Die Jobsuche in der Ukraine / ist ein schneller / und moderner Prozess.
- `человек`: Die Jobsuche in der Ukraine ist / ein schneller und moderner Prozess.

**[iter8-s15-chancen]** 15 слов · регистр: —
Diejenigen, die Flexibilität zeigen und über entsprechende Erfahrung verfügen, haben gute Chancen auf dem Arbeitsmarkt.

- `S5`: Diejenigen, die Flexibilität zeigen und / über entsprechende Erfahrung verfügen, haben / gute Chancen auf dem Arbeitsmarkt.
- `S1:d`: Diejenigen, die Flexibilität zeigen / und über entsprechende Erfahrung / verfügen, haben gute Chancen / auf dem Arbeitsmarkt.
- `S1`: Diejenigen, die Flexibilität zeigen / und über entsprechende Erfahrung verfügen, / haben gute Chancen / auf dem Arbeitsmarkt.
- `S4`: Diejenigen, die Flexibilität zeigen / und über entsprechende Erfahrung / verfügen, haben gute Chancen / auf dem Arbeitsmarkt.
- `человек`: Diejenigen, die Flexibilität zeigen / und über entsprechende Erfahrung verfügen, / haben gute Chancen / auf dem Arbeitsmarkt.

**[iter8-s16-aussichten]** 15 слов · регистр: —
Wer flexibel ist und die passende Erfahrung mitbringt, hat auf dem Arbeitsmarkt sehr gute Aussichten.

- `S5`: Wer flexibel ist und die / passende Erfahrung mitbringt, hat auf / dem Arbeitsmarkt sehr gute Aussichten.
- `S1:d`: Wer flexibel ist / und die passende Erfahrung mitbringt, / hat auf dem Arbeitsmarkt / sehr gute Aussichten.
- `S1`: Wer flexibel ist / und die passende Erfahrung mitbringt, / hat auf dem Arbeitsmarkt / sehr gute Aussichten.
- `S4`: Wer flexibel ist / und die passende Erfahrung mitbringt, / hat auf dem Arbeitsmarkt / sehr gute Aussichten.
- `человек`: Wer flexibel ist / und die passende Erfahrung mitbringt, / hat auf dem Arbeitsmarkt / sehr gute Aussichten.
