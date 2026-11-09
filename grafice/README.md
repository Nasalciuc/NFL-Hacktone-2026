# Graficele proiectului

Toate graficele, într-un singur loc. Sunt copii; originalele sunt în `dl_first_step/figures/` și `dl_first_step/outputs/`, iar `run_all.sh` le recopiază aici la fiecare rulare.

Ordinea figurilor urmează ipotezele: F3 = H1, F4 = H2, F5 = H3, F6 = H4. Culorile sunt aceleași peste tot: albastru = edge, portocaliu = interior, turcoaz = Combine.

## Graficele din lucrare (6)
| Fișier | Ce arată |
|---|---|
| `f1_speed_curves.png` | Viteza pass rusherilor după snap (mediana și jumătatea din mijloc a fazelor). Apoi aceeași viteză din momentul în care jucătorul atinge 1 yd/s, comparată cu sprintul de la Combine. Viteza interiorului se aplatizează aproape imediat, iar marcajele de pe axă arată unde se termină primul pas de 1,5 yarzi în meci. |
| `f2_reliability.png` | Stabilitatea măsurilor pe o singură încercare și pe jucător. Pe o încercare, Combine-ul e mult mai curat (0,60, față de 0,01 pentru un snap); pe jucător, meciurile câștigă prin volum (0,80 față de 0,75). |
| `f3_combine_vs_nfl.png` | **H1.** Primul pas la Combine față de cel din NFL, cu intervale de încredere și corecția pentru zgomotul de măsurare. Panoul din dreapta arată că nici ferestrele scurte, de dinainte de contact, nu arată transfer. |
| `f4_what_explains_nfl_first_step.png` | **H2.** Cât din primul pas din NFL explică rolul, greutatea și cele două timpi de la Combine, pe jucători lăsați în afara modelului, cu intervale de încredere. Nici timpul pe 10 yarzi, nici tracking-ul nu adaugă nimic peste rol și greutate. |
| `f5_pressure_vs_first_step.png` | **H3.** Presiunea pe zecimi ale primului pas din meci. Legătura rămâne și în cadrul aceluiași jucător (OR 0,72). Cea mai lentă zecime de la interior e marcată la marginea axei. |
| `f6_pressure_by_role.png` | **H4.** Primul pas la Combine față de rata de presiune, edge și interior. Legătura de la interior rezistă controlului pentru greutate și NT, dar e **exploratorie**. |

## Grafice de control (2)
Sunt făcute pentru verificare și nu intră în lucrare.

| Fișier | Ce arată |
|---|---|
| `check_h1_h4_rushers_only.png` | H1 și H4 pe cei 62 de jucători, cu definiția corectată a fazei de pass rush |
| `check_h1_h4_as_written.png` | Același grafic, cu definiția inițială din plan |
