# NFL Big Data Bowl 2027: primul pas al pass rusherilor (DL)

Analiza pentru [NFL Big Data Bowl 2027](https://www.kaggle.com/competitions/nfl-big-data-bowl-2027), cu tema *Combine to NFL Performance*. Termenul de predare este **6 ianuarie 2027, 23:59 UTC**.

**Întrebarea:** primul pas al unui jucător de linie defensivă (DL), măsurat cu senzorii de la Combine, se regăsește în primul pas din meciurile NFL și în presiunea pe quarterback?

**Răspunsul pe scurt:** get-off-ul din NFL are două părți: reacția la snap și accelerarea. Combine-ul nu are snap, deci măsoară doar accelerarea. Nici aceea nu se transmite în meci după ce ținem cont de greutate și de aliniere. În schimb, primul pas din meci e legat puternic de presiune.

## Rezultate (ipoteze scrise înainte de teste)
| Ipoteză | Rezultat | Verdict |
|---|---|---|
| H1: primul pas de la Combine → primul pas în NFL | r = +0,20 [−0,02; +0,45]; după greutate și aliniere: +0,02 | nesusținută (Holm p = 0,23) |
| H2: legătura cu reacția; comparația cu cronometrul | cu reacția r = +0,13; timpul oficial pe 10 yarzi explică 42%, tracking-ul 0% | descriptiv |
| H3: primul pas în meci → presiune | 12,5% presiune la 1 SD mai rapid față de 6,8% la 1 SD mai lent; OR 0,74 [0,65; 0,84] | **susținută** (Holm p < 0,001) |
| H4: Combine → presiune, peste draft și timpul pe 10 yarzi | −0,27 puncte procentuale pe SD; intervalul de încredere include 0 | nesusținută (Holm p = 0,47) |

Eșantionul principal are 62 de jucători DL din clasele de draft 2023–2025, cu cel puțin 50 de faze de pass rush în sezonul regulat. La nivel de fază sunt 26.120 de faze de la 98 de jucători.

## Structura
```
dl_first_step/           analiza principală
  ANALYSIS_PLAN.md       ipotezele, scrise înainte de teste, plus abaterile notate ulterior
  WRITEUP_DRAFT.md       prima variantă a lucrării pentru Kaggle (engleză, ~1.450 de cuvinte)
  common.py              încărcarea datelor, momentul de trecere peste un prag, timpul ancorat la 1 yd/s
  game_starts.py         primul pas și reacția în fazele de pass rush din meciuri
  combine_starts.py      primul pas la 40 de yarzi și în exercițiile DL de la Combine
  tests.py               testele H1–H4 și verificările de robustețe
  cv_h4.py               validarea leave-one-out pentru presiune (verificare descriptivă)
  figures.py             cele 6 grafice din lucrare
  figures/               graficele finale
  outputs/               jurnalele rulărilor și rezultatele JSON
wr_breaks/               verificarea receptorilor (WR): de ce nu continuăm pe ei
  WR_NOTES.md            concluzia
  wr_measures.py         măsurarea break-ului la Combine și în meciuri
  explore_wr.py          explorarea inițială
run_all.sh               reface toate rezultatele și graficele
requirements.txt         versiunile pachetelor folosite
```

## Cum se reface totul
1. Descarcă datele competiției de pe Kaggle și pune CSV-urile în folderul `nfl-big-data-bowl-2027/`, lângă `dl_first_step/`. **Datele nu sunt în repo**, pentru că regulile competiției interzic redistribuirea lor.
2. Instalează pachetele:
   ```bash
   pip install -r requirements.txt
   ```
3. Rulează tot:
   ```bash
   bash run_all.sh
   ```

Durează câteva minute pe un laptop. Fișierele `.parquet` intermediare se regenerează.

## Ce merită verificat
- **Definiția primului pas** (`common.py`, `anchored_measures`). Ceasul pornește când jucătorul atinge 1 yd/s, nu la primul cadru, pentru că înregistrările de la Combine încep cu jucătorul deja în mișcare.
- **Abaterile de la plan** (`ANALYSIS_PLAN.md`, secțiunea „Abateri”):
  - definiția fazei de pass rush exclude retragerile în acoperire;
  - `blitzing` a fost scos dintre variabilele de control;
  - formațiile rare sunt grupate.
  - Ambele variante sunt raportate (`outputs/tests_log.txt` și `outputs/tests_log_as_written.txt`).
- **Semnalul de la jucătorii de interior** (graficul F6) e explorator: una din circa 20 de verificări, deci nu e o concluzie.
- **Textul** (`WRITEUP_DRAFT.md`): fiecare cifră trebuie să se potrivească cu jurnalele din `outputs/`.

## Ce mai e de făcut
- Notebook-ul Kaggle public, obligatoriu la predare.
- Recitirea și finisarea textului.
