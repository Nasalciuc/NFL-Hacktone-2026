# NFL Big Data Bowl 2027: primul pas al pass rusherilor (DL)

Analiza pentru [NFL Big Data Bowl 2027](https://www.kaggle.com/competitions/nfl-big-data-bowl-2027), cu tema *Combine to NFL Performance*. Termenul de predare este **6 ianuarie 2027, 23:59 UTC**.

**Întrebarea:** primul pas al unui jucător de linie defensivă (DL), măsurat cu senzorii de la Combine, se regăsește în primul pas din meciurile NFL și în presiunea pe quarterback?

**Răspunsul pe scurt:** get-off-ul din NFL are două părți: reacția la snap și accelerarea. Combine-ul nu are snap, deci măsoară doar accelerarea. Nici aceea nu se transmite în meci după ce ținem cont de greutate și de aliniere. În schimb, primul pas din meci e legat puternic de presiune.

## Rezultate (ipoteze scrise înainte de teste)
| Ipoteză | Figură | Rezultat | Verdict |
|---|---|---|---|
| H1: primul pas de la Combine → primul pas în NFL | F3 | r = +0,20 [−0,02; +0,45]; după greutate și aliniere: +0,02 [−0,12; +0,16] | nesusținută (Holm p = 0,23) |
| H2: legătura cu reacția; comparația cu cronometrul | F4 | cu reacția r = +0,13; timpul oficial pe 10 yarzi explică 42%, tracking-ul 0%; niciunul nu adaugă peste rol și greutate | descriptiv |
| H3: faze cu prim pas mai rapid → mai multă presiune | F5 | 12,5% presiune la 1 SD mai rapid față de 6,8% la 1 SD mai lent; în cadrul aceluiași jucător OR 0,72 | **susținută** (Holm p < 0,001) |
| H4: Combine → presiune, peste draft și timpul pe 10 yarzi | F6 | −0,27 puncte procentuale pe SD; intervalul include 0; semnal explorator la interior | nesusținută (Holm p = 0,47) |

**Eșantioanele:**
- **La nivel de fază:** 26.120 de faze de pass rush din sezonul regulat, de la 98 de jucători DL (F1, F2 și F5).
- **La nivel de jucător:** dintre acești 98, 79 au cel puțin 50 de faze, iar 62 au și o repetare curată la 40 de yarzi (F3, F4 și F6).
- **Cine lipsește:** dintre cei 17 excluși, 16 au sărit peste 40 de yarzi. Ei au fost aleși mai devreme la draft și joacă mai mult pe edge, dar diferențele nu sunt clare statistic, iar rata lor de presiune e aceeași.

**A doua rundă de recenzie** a adăugat verificări post-hoc: fereastră scurtă de dinainte de contact, efecte fixe de jucător, controale pentru greutate și NT, stabilitate pe rol, corecția pentru atenuare și intervale pentru leave-one-out. Sunt în `dl_first_step/review_round2.py` și rezumate în `ANALYSIS_PLAN.md`.

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
  review_round2.py       verificările post-hoc cerute în a doua rundă de recenzie
  figures.py             cele 6 grafice din lucrare
  figures/               graficele finale
  outputs/               jurnalele rulărilor și rezultatele JSON
wr_breaks/               verificarea receptorilor (WR): de ce nu continuăm pe ei
  WR_NOTES.md            concluzia
  wr_measures.py         măsurarea break-ului la Combine și în meciuri
  explore_wr.py          explorarea inițială
grafice/                 toate graficele într-un singur loc, cu un index (README.md)
run_all.sh               reface toate rezultatele și graficele
requirements.txt         versiunile pachetelor folosite
```

## Cum se reface totul
**Datele nu sunt în repo.** Regulile competiției interzic redistribuirea lor, iar patru fișiere depășesc oricum limita GitHub de 100 MB. Fiecare membru al echipei le descarcă de pe Kaggle.

### 1. Acces la date
1. Intră în competiție pe [Kaggle](https://www.kaggle.com/competitions/nfl-big-data-bowl-2027) și acceptă regulile (**Join Competition**). Fără acest pas descărcarea dă eroarea 403.
2. Creează un token API: pe Kaggle, *Settings → API → Create New Token*. Se descarcă fișierul `kaggle.json`. Pune-l în `~/.kaggle/kaggle.json`; pe Windows, în `C:\Users\<nume>\.kaggle\kaggle.json`. Tokenul e personal: nu-l pune în repo și nu-l trimite nimănui.

### 2. Descarcă datele
Din folderul repo-ului:
```bash
pip install kaggle
```
```bash
kaggle competitions download -c nfl-big-data-bowl-2027 -p nfl-big-data-bowl-2027
```
```bash
unzip nfl-big-data-bowl-2027/nfl-big-data-bowl-2027.zip -d nfl-big-data-bowl-2027
```
Pe Windows, fără `unzip`, poți folosi PowerShell:
```powershell
Expand-Archive nfl-big-data-bowl-2027\nfl-big-data-bowl-2027.zip -DestinationPath nfl-big-data-bowl-2027
```

Arhiva are circa 2,2 GB după dezarhivare. Folderul `nfl-big-data-bowl-2027/` și arhivele `.zip` sunt excluse din git prin `.gitignore`.

### 3. Verifică fișierele
În `nfl-big-data-bowl-2027/` trebuie să fie direct aceste 9 CSV-uri:

| Fișier | Mărime aproximativă |
|---|---|
| `game_tracking_2025.csv` | 975 MB |
| `game_tracking_2024.csv` | 685 MB |
| `game_tracking_2023.csv` | 320 MB |
| `player_play.csv` | 140 MB |
| `combine_tracking.csv` | 80 MB |
| `combine_results.csv`, `games.csv`, `players.csv`, `player_career_successes.csv` | sub 0,1 MB fiecare |

Dacă după dezarhivare ajung într-un subfolder, dă calea acelui subfolder ca argument: `bash run_all.sh <cale>`.

### 4. Rulează analiza
```bash
pip install -r requirements.txt
```
```bash
bash run_all.sh
```

Durează circa 10 minute pe un laptop. Reface fișierele `.parquet`, jurnalele, rezultatele JSON și toate graficele, inclusiv folderul `grafice/`.

## Ce merită verificat
- **Definiția primului pas** (`common.py`, `anchored_measures`). Ceasul pornește când jucătorul atinge 1 yd/s, nu la primul cadru, pentru că înregistrările de la Combine încep cu jucătorul deja în mișcare.
- **Abaterile de la plan** (`ANALYSIS_PLAN.md`, secțiunea „Abateri”):
  - definiția fazei de pass rush exclude retragerile în acoperire;
  - `blitzing` a fost scos dintre variabilele de control;
  - formațiile rare sunt grupate.
  - Ambele variante sunt raportate (`outputs/tests_log.txt` și `outputs/tests_log_as_written.txt`).
- **Semnalul de la jucătorii de interior** (graficul F6) e explorator: una din circa 20 de verificări. Rezistă controlului pentru greutate și NT, dar p = 0,003 e peste pragul Bonferroni de 0,0025.
- **Textul** (`WRITEUP_DRAFT.md`): fiecare cifră trebuie să se potrivească cu jurnalele din `outputs/`.

## Ce mai e de făcut
- Notebook-ul Kaggle public, obligatoriu la predare.
- Recitirea și finisarea textului.
