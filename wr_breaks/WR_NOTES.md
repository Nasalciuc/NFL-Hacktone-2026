# WR: ce am verificat și de ce nu continuăm (9 noiembrie 2026)

Scopul a fost să vedem dacă receptorii oferă o legătură Combine–NFL mai bună decât primul pas al DL.
Am verificat doar măsurătorile și stabilitatea lor. Nu am testat nicio legătură cu rezultatele din meciuri, pentru că măsurile nu erau destul de stabile ca un astfel de test să aibă sens.

## Ce există
- 107 receptori la Combine, cu circa 10 rute fiecare. Aproape fiecare rută are **o singură repetare**.
- 35.427 de rute în sezonul regulat (83 de receptori). Separarea la momentul pasei e completată la 99,6% din rutele în care pasa a fost aruncată.

## Măsura: frânarea în break
Break-ul e găsit după viteză: după ce receptorul trece de 4,5 yarzi/s, break-ul începe când viteza scade sub 70% (sau 80%) din maximul atins. Măsurăm decelerarea, procentul de viteză pierdut și reaccelerarea (`wr_measures.py`).

| Verificare | Rezultat |
|---|---|
| Exerciții de Combine cu break detectat la ≥ 80% din repetări | comeback, curl, slot strike |
| Stabilitatea între exerciții diferite, același jucător | 0,26–0,35 (prea mică) |
| Rute din meci cu break detectat la ≥ 50% din cazuri | doar hitch |
| Jucători cu ≥ 25 de break-uri în fiecare jumătate de meciuri | 17–22 |
| Stabilitatea separării la nivel de jucător (meciuri pare/impare) | 0,80, rezultat bun |

## Alte idei verificate
| Măsură | Stabilitate |
|---|---|
| Gauntlet: viteza medie (2 repetări pe jucător) | 0,71, dar e practic viteza de la 40 de yarzi |
| Gauntlet: viteza păstrată la prinderi | 0,25 |
| Gauntlet: cea mai mare scădere de viteză | 0,50 |
| Yarzi după prindere peste așteptări (meciuri) | 0,11–0,13, aproape zgomot |

## Concluzie
- **Problema WR e măsurarea la Combine, nu rezultatul din meci.** Separarea e stabilă (0,80), dar break-ul măsurat la Combine nu e o trăsătură stabilă a jucătorului.
- **Puterea testului ar fi prea mică.** O legătură reală ar fi atenuată cam la jumătate. Cu circa 65 de jucători, s-ar putea demonstra doar o legătură reală foarte mare (peste circa 0,7), ceea ce e puțin plauzibil.
- **Decizia:** rămânem pe DL. WR poate apărea în lucrare doar ca o comparație de stabilitate între grupe de poziții.
