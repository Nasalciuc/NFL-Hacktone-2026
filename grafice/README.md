# Graficele proiectului

Toate graficele produse până acum, într-un singur loc. Sunt copii: originalele rămân în `dl_first_step/figures/` și `dl_first_step/outputs/`. `run_all.sh` le recopiază aici la fiecare rulare.

## Graficele din lucrare (6)
| Fișier | Ce arată | În lucrare |
|---|---|---|
| `f1_speed_curves.png` | Viteza medie a pass rusherilor după snap, edge și interior. Apoi aceeași viteză din momentul în care jucătorul atinge 1 yd/s, comparată cu sprintul de 40 de yarzi de la Combine. Get-off-ul are două părți, iar Combine-ul o are doar pe a doua. | Figura 1 |
| `f2_reliability.png` | Cât de stabile sunt măsurile la Combine și în meciurile NFL, plus măsurile WR pentru comparație. În meciuri primul pas se măsoară mult mai sigur (0,94) decât la Combine (0,75). | Figura 2 |
| `f3_pressure_vs_first_step.png` | Procentul de faze cu presiune, pe zecimi ale primului pas din meci, separat pentru edge și interior. Un prim pas mai rapid merge cu mai multă presiune: 12,5% față de 6,8%. | Figura 3 (H3) |
| `f4_combine_vs_nfl.png` | Primul pas la Combine față de primul pas din NFL, pentru 62 de jucători. Nu se transmite: r = +0,20, iar după greutate și aliniere aproape 0. | Figura 4 (H1) |
| `f5_what_explains_nfl_first_step.png` | Cât din primul pas din NFL explică fiecare factor, pe jucători lăsați în afara modelului. Alinierea și greutatea explică mult, primul pas de la Combine nimic. | Figura 5 (H2) |
| `f6_pressure_by_role.png` | Primul pas la Combine față de rata de presiune, separat edge și interior. Apare o legătură doar la interior (r = −0,49), dar e **exploratorie**. | Figura 6 (H4) |

## Grafice de control (2)
Au fost făcute pentru verificare, ca să vedem dacă un jucător extrem schimbă rezultatul. Nu intră în lucrare.

| Fișier | Ce arată |
|---|---|
| `check_h1_h4_rushers_only.png` | H1 și H4 pe toți cei 62 de jucători, cu definiția corectată a fazei de pass rush (doar fazele în care jucătorul a atacat) |
| `check_h1_h4_as_written.png` | Același grafic, cu definiția inițială din plan |
