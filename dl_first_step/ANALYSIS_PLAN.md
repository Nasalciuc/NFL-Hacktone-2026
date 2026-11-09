# Planul analizei: primul pas al pass rusherilor (DL)

Scris pe 9 noiembrie 2026, **înainte** de orice test al legăturii dintre Combine și NFL.
Măsurile de mai jos au fost alese doar după cât de bine măsoară, fără să ne uităm la rezultatele din NFL.

## Întrebarea
Poate tracking-ul de la Combine să măsoare primul pas al unui pass rusher mai bine decât cronometrul? Și se vede acest prim pas în sezonul regulat NFL, în primul pas din meciuri și în presiunea pe quarterback?

## Datele folosite
- **Jucători:** cei înscriși la Combine ca DL (118).
- **Faze din meciuri:** sezonul regulat 2023–2025, faze de pass rush (coloana `sack` completată), aliniere `EDGE` sau `INTERIOR_LINE`. Fazele anulate de penalizări sunt excluse.
- **Start din poziție statică:** viteza la snap sub 1 yard/s (96% din faze).
- **Combine:** repetările la 40 de yarzi cu start curat, adică viteza în primul cadru sub 1 yard/s.
- **Eșantion principal:** jucătorii cu cel puțin 50 de faze eligibile și o repetare curată la 40 de yarzi. Sunt **62 de jucători** (clasa 2023: 25, 2024: 23, 2025: 14).

## Măsurile

### Problema startului
La Combine, înregistrarea începe când jucătorul e deja în mișcare, iar momentul tăierii variază. Din acest motiv, timpul de 10 yarzi calculat din primul cadru se potrivește slab cu cel oficial (r = 0,47). Toate măsurile de mai jos pornesc de aceea din momentul în care **viteza atinge 1 yard/s** și din poziția din acel moment. Definiția e identică la Combine și în meciuri.

| Măsură | Definiție | Unde |
|---|---|---|
| `burst_15` | secunde pentru a parcurge 1,5 yarzi în linie dreaptă din momentul în care viteza atinge 1 yard/s | Combine (40 de yarzi) și meciuri |
| `burst_25` | la fel, pe 2,5 yarzi | ambele |
| `acc_1to3` | secunde de la 1 la 3 yarzi/s | ambele |
| `t_react` | secunde de la snap până la 1 yard/s | doar meciuri |
| `pressure` | jucătorul a creat presiune (`time_to_pressure` completat) | doar meciuri |

- **La Combine:** media repetărilor curate.
- **În meciuri:** media fazelor eligibile ale jucătorului.
- **Comparatori tradiționali:** timpul oficial pe 10 yarzi (`ten_yd_split`), greutatea și locul la draft.

**Măsura principală este `burst_15`:**
- în meciuri se termină de obicei înainte de contactul cu blocatorul (mediana 0,66 s);
- există pentru 99,9% din faze;
- există pentru 93 de jucători DL la Combine.

## Verificări de măsurare deja făcute
| Verificare | Rezultat |
|---|---|
| Timpul de 40 de yarzi din tracking față de cel oficial | r = 0,91, decalaj constant de +0,32 s |
| Stabilitatea între încercări la 40 de yarzi, DL (73 de jucători) | `burst_15` 0,60, `burst_25` 0,63, `acc_1to3` 0,66 |
| Stabilitatea între meciuri pare și impare (74 de jucători) | `burst_15` 0,92, `burst_25` 0,94, `acc_1to3` 0,97, `t_react` 0,82 |
| Corelația cu get-off-ul oficial NGS, pe fază | `t_react` 0,62, `burst_15` 0,54, `t_react + burst_25` 0,64 |
| `forty_burst25` față de timpul oficial pe 10 yarzi | r = 0,25 (măsoară altceva) |
| Timpul oficial pe 10 yarzi față de greutate | r = 0,86 |
| Exercițiul de pass rush, stabilitate între repetări | 0,14–0,27, deci exclus |
| Exercițiul front start, corelația cu primul pas la 40 de yarzi | −0,01, deci exclus |

- **Calcul propriu:** get-off-ul oficial NGS nu poate fi reprodus exact fără poziția mingii. De aceea calculăm noi măsurile din meciuri și folosim coloana oficială doar ca verificare.
- **Linia de scrimmage aproximativă:** linia calculată din `yardline_number` are o eroare de circa ±0,5 yarzi; 5% dintre jucători par în spatele ei la snap.

## Ipoteze (fiecare testată o singură dată)
**H1, transferul.** `burst_15` la Combine este corelat pozitiv cu `burst_15` din meciuri. Testăm cu corelația Pearson și interval de încredere bootstrap de 95%, apoi cu regresie controlată pentru greutate și pentru proporția fazelor pe `EDGE`.

**H2, specificitatea.** `burst_15` la Combine are o legătură slabă cu reacția la snap (`t_react`), pentru că la Combine nu există snap. Raportăm corelația și intervalul ei de încredere. Comparăm apoi cât din `burst_15` din meciuri explică primul pas din tracking față de timpul oficial pe 10 yarzi, cu validare încrucișată leave-one-out.

**H3, primul pas și presiunea.** La nivel de fază, un `burst_15` mai rapid crește probabilitatea de presiune. Folosim regresie logistică cu `burst_15` standardizat pe aliniere și `t_react`. Contextul controlat este alinierea, down-ul, yarzii de parcurs, blitz-ul, formația ofensivei și diferența de scor. Erorile standard sunt grupate pe jucător.

**H4, de la Combine la presiune.** `burst_15` la Combine prezice rata de presiune a jucătorului peste ce explică locul la draft și timpul oficial pe 10 yarzi. Rata de presiune e corectată pentru numărul de faze cu un model beta-binomial empiric. Facem regresie la nivel de jucător, cu interval de încredere bootstrap.

Testele principale sunt H1, H3 și H4, cu corecția Holm la α = 0,05. H2 e descriptiv.

## Verificări de robustețe
- prag de 30 și de 100 de faze în loc de 50;
- `burst_25` și `acc_1to3` în loc de `burst_15`;
- corelația Spearman;
- fiecare clasă de draft separat;
- doar `EDGE` și doar `INTERIOR_LINE`;
- fără presiunile neblocate (`unblocked_pressure`);
- `dropback_duration` adăugat în modelul H3.

## Abateri de la plan (9 noiembrie 2026, după prima rulare)
1. **Definiția fazei de pass rush.** Coloana `sack` completată include și 1.256 de faze (4,6%) în care jucătorul s-a retras în acoperire (`blitzing` = fals). Acolo nu a existat nicio presiune. Varianta corectată păstrează doar fazele în care jucătorul a atacat. Rezultatele cu definiția inițială sunt raportate alături.
2. **Variabila „blitz” scoasă din H3.** Pentru jucătorii DL, `blitzing` arată dacă jucătorul a atacat, nu dacă echipa a trimis blitz. Folosită ca variabilă de control, producea separare perfectă și modelul nu convergea. Datele nu permit calculul unui blitz al echipei, pentru că nu avem toți cei 11 apărători.
3. **Formațiile rare.** Formațiile cu sub 100 de faze (`WILDCAT`, valori lipsă) sunt grupate ca `OTHER`, pentru a putea fi estimate.
4. **Fără verificarea cu `dropback_duration`.** Coloana e goală pentru toate fazele DL, deci această verificare de robustețe nu se poate face.

5. **Verificare descriptivă adăugată după teste (`cv_h4.py`).** Pentru a acoperi punctul din planul pe săptămâni („validare încrucișată cu control pentru draft”), am calculat și leave-one-out pentru rata de presiune. Locul la draft, timpul pe 10 yarzi și alinierea explică 44% din diferențele dintre jucători; cu primul pas de la Combine adăugat, 42%. Nu e un test nou, iar rezultatul H4 rămâne cel din `tests.py`.

Primele rezultate H1, H2 și H4 nu depind de regresia logistică și au fost calculate exact ca în plan. Ele sunt identice în varianta cu definiția inițială.

## A doua rundă de recenzie (post-hoc, 9 noiembrie 2026)
Toate verificările de aici au fost cerute de un coleg după ce rezultatele erau cunoscute. Ele nu schimbă testele H1–H4 și sunt marcate în lucrare ca *post-hoc*. Codul e în `review_round2.py`, jurnalul în `outputs/review_round2_log.txt`.

| Cerere | Rezultat |
|---|---|
| Fereastră mai scurtă, înainte de contact (0,5 yarzi; accelerația în primele 0,2 s) | Nicio fereastră nu arată transfer. Cel mai aproape: accelerația timpurie la interior, r = +0,28 [−0,03; +0,55] |
| Viteza de circa 0,3 yd/s la snap | Mișcarea începe cu circa 0,2 s înainte de cadrul snap-ului. Viteza calculată din poziție arată aceeași creștere, deci nu e un efect de netezire |
| Mediană cu bandă interquartilă în F1 | Făcut |
| Rândul „Rol + greutate + timpul pe 10 yarzi” și intervale pentru leave-one-out | Timpul pe 10 yarzi scade acuratețea cu −0,017 [−0,034; −0,005]; corelația lui cu greutatea e 0,84 |
| H3 între jucători și în cadrul aceluiași jucător | Cu efecte fixe de jucător: OR 0,72 [0,65; 0,80]. Și pe fereastra de 0,5 yarzi: OR 0,86 [0,80; 0,91] |
| Interiorul controlat pentru greutate și NT | r parțial −0,48 [−0,70; −0,10]; eliminând pe rând câte un jucător, între −0,53 și −0,40; Spearman −0,46; p = 0,003, peste pragul Bonferroni de 0,0025 |
| Shrinkage spre media rolului | Mediile: edge 10,5%, interior 6,5%. Rezultatele rămân aceleași |
| Stabilitatea pe rol și pe o singură încercare | Un snap NFL: 0,01. O încercare la Combine: 0,60. Sezonul, ajustat pe rol: 0,80 (era 0,94 cu rolurile amestecate) |
| Corecția pentru atenuare | Plafonul corelației observabile e 0,77; estimarea corectată e +0,05 [−0,24; +0,38] |
| Jucătorii lipsă din eșantion (17) | 16 au sărit peste 40 de yarzi. Au fost aleși mai devreme la draft (mediana 66 față de 124) și joacă mai mult pe edge; diferențele nu sunt clare statistic |
| Ordinea figurilor și culorile | Figurile urmează acum H1–H4. Graficele de control folosesc aceleași culori ca lucrarea |

## Ce nu putem afirma
- **Eșantion mic:** 62 de jucători; doar corelațiile de peste circa 0,35 pot fi demonstrate sigur.
- **Selecție:** apar doar jucătorii care au jucat suficient; cei care n-au prins echipa lipsesc din H1, H3 și H4.
- **Cauzalitate:** nu se poate demonstra; locul la draft influențează și timpul de joc, și calitatea coechipierilor.
- **Clasa 2025:** are un singur sezon jucat.
