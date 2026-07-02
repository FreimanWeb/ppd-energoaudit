# Карта соответствия: Методика (разд. 8, формулы 7–47) → код → тесты

Аудит от 02.07.2026. Эталон — «НТУ цифровая платформа/Методика энергоаудита.pdf»
(15 стр., разд. 8 «Методика расчёта потерь энергии в насосных установках и агрегатах»).
Каждая формула сверена с PDF по буквальному тексту: выражение, коэффициенты, единицы,
граничные условия. Колонка «Соответствие» — итог сверки; расшифровка отклонений в
примечаниях под таблицами и в `docs/audit_findings.md`.

Соглашения ядра по единицам (`units.py`): p — МПа, Q — м³/ч, H — м, ρ — кг/м³,
P — кВт, W — кВт·ч, УРЭ — кВт·ч/м³; g = 9,81; кгс/см² → МПа ×0,098 (как в PDF).

## 8.3 Расчётные параметры режима (7)–(16)

| № | Формула | Реализация | Тест | Соответствие |
|---|---|---|---|---|
| (7) | Q_ср = Q_сут/T | `spec.py::RegimeMeasurement.flow()` (q_day/t; приоритет — измеренная q_fact) | `tests/verification/test_objects.py::test_measured_kpi_reproduced` (через подачу всех агрегатов) | ✓ |
| (8) | H_ф = (p_вых−p_вх)·10⁶/(ρ·g) | `units.py::head_from_pressure`, вызов в `core/pump.py::compute_regime` | `test_units.py::test_head_from_pressure_dns7s`, `test_dns7s.py::test_head_and_powers` | ✓ |
| (9) | Δp_задв = p_вых − p_БГ | `core/pump.py::compute_regime` (`dp_valve`) | `test_core.py::test_kns_decomposition_sums_to_electric` | ✓ |
| (10) | H_БГ = (p_БГ−p_вх)·10⁶/(ρ·g) | `core/pump.py::compute_regime` (`h_bg`) | покрыт тем же прогоном (величина информационная) | ✓ |
| (11) | P_гидр = (p_вых−p_вх)·Q/3,6 | `units.py::hydraulic_power_kw` | `test_units.py::test_hydraulic_power_dns7s`, `test_dns7s.py::test_head_and_powers` | ✓ |
| (12) | P_эл.ср = W/T | `core/pump.py::compute_regime` (ветка `w/t`), `core/audit.py` | verification: объекты с задан W (все КНС из xlsx) | ✓ |
| (13) | η_НУ = P_гидр/P_эл | `core/pump.py::compute_regime` (`eta_unit`) | `test_dns7s.py::test_efficiencies`, verification «КПД факт» | ✓ |
| (14) | η_ном = η_ЭДном·η_нас.ном | `core/pump.py::nominal_efficiency`, `spec.py::AggregateSpec.nominal_efficiency` | `test_core.py::test_nominal_efficiency_14` | ✓ |
| (15) | η_ном = η_пч·η_ЭДном·η_тр·η_нас.ном | те же ф-ции, η_пч=0,97 при `vfd: true` (как в PDF, стр. 4: «принимаем η_пч = 0,97») | `test_core.py::test_formula_15_with_vfd_and_gear` | ✓ |
| (16) | УРЭ_ф = P_эл.ср/Q_ср = W/Q_сут | `core/specific_energy.py::sec_fact`; в `audit.py` приоритет W/Q_сут, запас — P_эл/Q | `test_dns7s.py::test_specific_energy`, verification «УРЭ факт» (11 агрегатов, 100 %) | ✓ |

## УРЭ и характеристика трубопровода (17)–(23)

| № | Формула | Реализация | Тест | Соответствие |
|---|---|---|---|---|
| (17) | УРЭ_р = (p_вых−p_вх)/(3,6·η_ном) | `specific_energy.py::sec_calc` | `test_dns7s.py::test_specific_energy`, verification «УРЭ расчётный» | ✓ |
| (18) | УРЭ_опт = (p_опт−p_вх)/(3,6·η_ндт) | `specific_energy.py::sec_optimal`; для КНС p_опт=p_БГ (как в PDF) | `test_core.py::test_sec_optimal_uses_ndt` | ✓ с допущением: **η_ндт принят = η_ном** (реестра НДТ нет — см. findings §Д1) |
| (19) | H_т = H_с + K_т·Q² | `specific_energy.py::PipeCharacteristic.head` | `test_core.py::test_pipe_characteristic_and_optimal_pressure` | ✓ |
| (20) | H_с ≈ (p_пп−p_вх)·10⁶/(ρg) + h_пп − h | `specific_energy.py::pipe_characteristic` | там же | ✓ |
| (21) | K_т = (H_ф−H_с)/Q² | `specific_energy.py::pipe_characteristic` | там же | ✓ |
| (22) | Q_прит = Q_сут/24 | `specific_energy.py::optimal_pressure` | там же | ✓ |
| (23) | p_опт = ρ·g·(H_с+K_т·Q_прит²)·10⁻⁶ | `specific_energy.py::optimal_pressure` | там же | ✓ |

## Электродвигатель (24)–(27)

| № | Формула | Реализация | Тест | Соответствие |
|---|---|---|---|---|
| (24) | K_з = P_эл/(P_ном/η_ЭДном) | `core/motor.py::load_factor` | `test_dns7s.py::test_load_factor`, verification «K загрузки ЭД» | ✓; отчёт №31 отображает K_з=P_эл/P_ном — задокументировано в docstring |
| (25) | η_эд.р = 1/(1+(1/η_ном−1)β) при K_з<0,7 | `core/motor.py::motor_efficiency` | `test_core.py::test_motor_efficiency_branches`, `test_dns7s.py::test_efficiencies` | ✓; при K_з≥0,7 → η_ном (граница PDF «0,7…1,0» соблюдена; K_з>1 тоже → η_ном, PDF перегрузку не оговаривает) |
| (26) | β = (α/K_з+K_з)/(1+α) | `core/motor.py::motor_efficiency` | там же | ✓; α: асинхр. 1,0 / синхр. 2,0 (`spec.py::MotorSpec.alpha`, PDF: «0,5…1 … до 2») |
| (27) | η_нас = η_НА/(η_эд.р·η_пч·η_ред) | `core/motor.py::pump_efficiency` | `test_dns7s.py::test_efficiencies`, `test_core.py::test_formula_27_with_vfd_gear` | ✓ (исправлено 02.07.2026: η_пч/η_ред теперь прокидываются из спеца агрегата — ранее при ПЧ/редукторе молча принимались = 1) |

## Рабочая точка и вязкость (28)–(30)

| № | Формула | Реализация | Тест | Соответствие |
|---|---|---|---|---|
| (28) | Re = Q_ном·10⁷/(9π·ν·(D−d)) | `core/curves.py::reynolds` | `test_core.py::test_reynolds_and_viscosity_factors` | ⚠ **отступление от буквы PDF**: код использует внутренний диаметр D−2d (d — толщина стенки, внутренний диаметр = D−2d физически); PDF пишет (D−d). Влияние — только на нефтеперекачку с вязкой жидкостью (в текущей верификации таких нет). Вопрос заказчику — findings §В1 |
| — | K_Q, K_H, K_η по номограмме рис. 8.4.1 | `core/curves.py::viscosity_factors` — **заглушка** (K=1 при Re≥10⁵, грубая оценка ниже) | `test_reynolds_and_viscosity_factors` (только ветка K=1) | ⚠ номограмма НЕ оцифрована; калибровочная точка PDF: Re=400 → K_Q=0,72, K_H=0,815, K_η=0,385 — заглушка даёт (1,0/0,81/0,76). Для воды ППД (Re≥10⁵) корректно K=1. Бэклог — findings §Б1 |
| (29) | H_д = aQ²+bQ+c | `core/curves.py::fit_parabola`+`head_due`; подключено в `audit.py` при наличии `curve_qh` | `test_core.py::test_parabola_fit`, `test_head_due_from_curve` | ✓ (подключено к оркестратору 02.07.2026 — ранее функция была, но не вызывалась) |
| (30) | η_д = uQ²+vQ+w | `core/curves.py::eta_due`; в `audit.py` при наличии `curve_qeta`, иначе `eta_pump_due` из паспорта/отчёта, иначе η_нас.ном | `test_parabola_fit`, `test_eta_due_from_curve`; ДНС-7с: η_д=0,576 из отчёта №31 | ✓ (та же оговорка) |

## Декомпозиция потерь КНС (31)–(36)

| № | Формула | Реализация | Тест | Соответствие |
|---|---|---|---|---|
| (31) | ΔP_гидр = Δp_задв·Q/3,6 | `core/pump.py::decompose_kns`; отдельно для ЗРА — `core/zra.py::throttle_loss` | `test_core.py::test_kns_decomposition_sums_to_electric`, `test_chain.py::test_throttle_loss` | ✓ |
| (32) | ΔP_др = ΔP_гидр/η_ном | `decompose_kns` / `zra.throttle_loss` | там же | ✓ |
| (33) | ΔP_НАдр = ΔP_гидр/η_ном − ΔP_гидр | `decompose_kns` | `test_kns_decomposition_sums_to_electric` (ΔP_гидр+ΔP_НАдр = ΔP_др) | ✓ |
| (34) | P_БГ = P_гидр − ΔP_гидр | `decompose_kns` (`p_bg_useful`) | там же | ✓ |
| (35) | ΔP_ном = P_БГ/η_ном − P_БГ | `decompose_kns` | там же | ✓ |
| (36) | ΔP_КПД = P_эл − ΔP_ном − ΔP_др − P_БГ | `decompose_kns` | там же + негативный `test_kns_decomposition_negative_no_pbg` | ✓; 5-частная диаграмма (рис. 8.5.1) = `components`, Σ = P_эл |

## Декомпозиция потерь перекачки (37)–(43)

| № | Формула | Реализация | Тест | Соответствие |
|---|---|---|---|---|
| (37) | ΔP_ном = P_гидр·(1/η_ном−1) | `core/pump.py::decompose_pumping` | `test_dns7s.py::test_power_balance_43` (в составе) | ✓ |
| (38) | ΔP_КПД = P_гидр·(1/η_НА−1/η_ном) | `decompose_pumping` | `test_dns7s.py::test_annual_efficiency_loss` (ΔW_НА=ΔP_КПД·T=53 242,9 — эталон №31) | ✓ |
| (39) | ΔP_неопт = P_гидр·(1/(η_д·η_ЭДном)−1/η_ном) | `decompose_pumping` | `test_power_balance_43` | ✓ |
| (40) | ΔP_вязк = (P_гидр/η_ЭДном)·(1/η_д.в−1/η_д) | `decompose_pumping`; η_д.в = η_д·K_η (при K_η=1 → 0) | `test_power_balance_43` | ✓ |
| (41) | ΔP_ЭД = P_эл − P_гидр/(η_нас·η_ЭДном) | `decompose_pumping` | `test_power_balance_43` | ✓ |
| (42) | ΔP_изн = (P_гидр/η_ЭДном)·(1/η_нас−1/η_д.в) | `decompose_pumping` | `test_power_balance_43` | ✓ |
| (43) | Баланс: ΔP_КПД = ΔP_вязк+ΔP_неопт+ΔP_ЭД+ΔP_изн | `decompose_pumping` (`balance_residual`, `balance_ok`, допуск 1e-6 кВт) | `test_power_balance_43` + негативный `test_core.py::test_balance_43_detects_inconsistency` | ✓ |

## Годовые потери (44)–(47)

| № | Формула | Реализация | Тест | Соответствие |
|---|---|---|---|---|
| (44) | ΔW_кпд = Q_год·(УРЭ_ф−УРЭ_р) | `specific_energy.py::annual_loss_efficiency_by_sec`; в `audit.py` база Q_год = Q_факт·T_год (соглашение инженеров в xlsx, сверено) | `test_core.py::test_annual_losses_44_47`, verification «ΔW КПД» | ✓ |
| — | ΔW_кпд через мощность (эквивалент при разовом замере) | `annual_loss_efficiency_by_power` = ΔP_КПД(38)·T_год | `test_dns7s.py::test_annual_efficiency_loss` | ✓ (тождественно (44) при УРЭ_ф=P_эл/Q — доказано алгебраически, см. docstring) |
| (45) | ΔW_др = (p_вых−p_БГ)/(3,6·η_ном)·Q_год | `specific_energy.py::annual_loss_throttle`, `zra.py::throttle_loss` | `test_annual_losses_44_47`, `test_throttle_loss`, verification «ΔW дрос» | ✓ |
| (46) | ΔW_ц = (p_вых−p_опт)/(3,6·η_ном)·Q_год | `specific_energy.py::annual_loss_cyclic` | `test_core.py::test_annual_loss_cyclic` | ✓ формула; **не подключена к оркестратору** — нет объекта с задокументированным цикл. режимом (ДНС-7с работает непрерывно); бэклог findings §Б2 |
| (47) | ΔW_ндт = Q_год·(УРЭ_ф−УРЭ_опт) | `specific_energy.py::annual_loss_ndt` | `test_annual_losses_44_47` | ✓ формула; в оркестраторе не выводится отдельной строкой (нет η_ндт — см. (18)) |

## Исходные данные (8.2, табл. 8.2.1)

Перечень измеряемых параметров → `spec.py::RegimeMeasurement` (все 14 позиций
представимы; ν/D/d — поля `nu` и паспорт трубопровода в `config/topology`).
Перевод кгс/см²→МПа ×0,098 — `units.py::kgfcm2_to_mpa` (тест `test_units.py::test_kgfcm2_to_mpa`).
Паспортные данные → `PumpSpec`/`MotorSpec` (+ `curve_qh`, `curve_qeta` — таблицы координат,
как «приложение Д Инструкции» из PDF). Телеметрия задаётся картой `telemetry` в
`config/plants/<id>.yaml` (см. «Контракт телеметрии» в Vault).

## Сверх методики (по ТЗ — вся цепочка ППД)

PDF разд. 8 покрывает только насосные установки/агрегаты. Требования ТЗ п.7.1
закрываются модулями вне методики (стандартная инженерная гидравлика):

| Узел ТЗ | Реализация | Тест |
|---|---|---|
| Водоводы (гидрорасчёт, неучтённые потери) | `core/hydraulics.py` (Дарси–Вейсбах/Свами–Джейн, Хазен–Вильямс, статика; неучтённые = Δp_факт−Δp_расч, порог 10 %) | `test_chain.py` (5 тестов), `test_dns7s.py::test_unaccounted_hydraulic_losses` (эталон №31: 6,5 %) |
| ЗРА/штуцеры | `core/zra.py` (по (31)–(33),(45)) | `test_chain.py::test_throttle_loss` |
| Распредузлы | `core/nodes.py` (матбаланс, локализация невязок) | `test_material_balance*` |
| Нагнетательные скважины | `core/wells.py` (индикаторная P–Q, приёмистость, лимиты) | `test_injectivity_*` |
| Пласт (отклик) | `core/reservoir/` (интерфейс + Demo + CRM-lite) | `test_reservoir_*` |
| Карта потерь / декомпозиция УРЭ | `decomposition.py` (Σ статей = P_эл) | `test_loss_map_sums_to_electric` |
| Мероприятия + ТЭО | `measures/registry.py` | `test_measures_suggested` |
| Оптимизация уставок | `optimize/setpoints.py` | `test_setpoint_optimization` |
| Балансы данных (объём УУЖ↔перекачка, энергия, УРЭ факт) | `quality/balances.py` | `test_ingest.py` + негативные `tests/test_quality.py` (баланс ловит невязку −20 %, пустое пересечение периодов) |

## Что НЕ реализовано (безнаказанно не дописывалось — бэклог)

См. `docs/audit_findings.md`, раздел «Бэклог»: номограмма вязкости 8.4.1 (§Б1),
ΔW_ц в оркестраторе (§Б2), реестр НДТ для η_ндт (§Д1), гидрорасчёт сети водоводов
по участкам с телеметрией (§Б3), диагностические правила рабочей зоны 0,8–1,2·Q_ном (§Б4).
