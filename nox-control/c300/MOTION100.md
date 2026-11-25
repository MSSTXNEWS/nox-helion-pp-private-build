# MOTION100: 100 анимаций NOX (K5)

Источник: собственные пресеты (CSS @keyframes + GSAP keyframes), написанные в духе перечисленных открытых библиотек. Код сторонних библиотек НЕ копировался и не скачивался (Animate.css, Hover.css, Magic.css, AutoAnimate в vendor отсутствуют; GSAP, Motion, Lottie-web есть в vendor).
Лицензия кода пресетов: проект NOX (свой код). Вдохновение/названия приёмов: Animate.css (MIT, bounce/tada/jello/rubberBand/shakeX/headShake/flash/fadeIn*), Hover.css (MIT, float/bob/pulse/wobble), Magic.css (MIT, puffIn/swap-перспектива), GSAP (Standard no-charge, vendor/gsap, исполнитель keyframes), AutoAnimate (MIT, идея мягких входов).
Файлы: site/nox-k5-motion100.css (классы .anm-001…100), site/nox-k5-motion100.js (NOXMotion.play(el,id|состояние), пресеты GSAP, привязка к состояниям).
Применено: chat.html (талисман #k5-mc, состояния idle/listen->ожидание, think->думает, speak->говорит; переход страницы), index.html и voice.html (переход страницы, NOXMotion.state(name) для радости/тревоги).

| ID | Состояние | Название | Длит., с | Повторы | Где применено |
|---|---|---|---|---|---|
| ANM-001 | ожидание | float-3 | 3.2 | infinite | талисман/#page |
| ANM-002 | ожидание | float-5 | 3.2 | infinite | талисман/#page |
| ANM-003 | ожидание | float-8 | 3.2 | infinite | талисман/#page |
| ANM-004 | ожидание | float-12 | 3.2 | infinite | талисман/#page |
| ANM-005 | ожидание | breathe-1.02 | 3.6 | infinite | талисман/#page |
| ANM-006 | ожидание | breathe-1.04 | 3.6 | infinite | талисман/#page |
| ANM-007 | ожидание | breathe-1.07 | 3.6 | infinite | талисман/#page |
| ANM-008 | ожидание | sway-2 | 4 | infinite | талисман/#page |
| ANM-009 | ожидание | sway-4 | 4 | infinite | талисман/#page |
| ANM-010 | ожидание | sway-7 | 4 | infinite | талисман/#page |
| ANM-011 | ожидание | glow-1.1 | 2.8 | infinite | талисман/#page |
| ANM-012 | ожидание | glow-1.25 | 2.8 | infinite | талисман/#page |
| ANM-013 | ожидание | glow-1.4 | 2.8 | infinite | талисман/#page |
| ANM-014 | ожидание | drift-4 | 5 | infinite | талисман/#page |
| ANM-015 | ожидание | drift-8 | 5 | infinite | талисман/#page |
| ANM-016 | ожидание | hue-10 | 6 | infinite | талисман/#page |
| ANM-017 | ожидание | hue-25 | 6 | infinite | талисман/#page |
| ANM-018 | ожидание | tilt-6 | 4.5 | infinite | талисман/#page |
| ANM-019 | ожидание | tilt-12 | 4.5 | infinite | талисман/#page |
| ANM-020 | ожидание | blink-soft | 3 | infinite | талисман/#page |
| ANM-021 | думает | spin-1.6 | 1.6 | infinite | талисман/#page |
| ANM-022 | думает | spin-2.4 | 2.4 | infinite | талисман/#page |
| ANM-023 | думает | spin-3.2 | 3.2 | infinite | талисман/#page |
| ANM-024 | думает | orbit-4 | 2.2 | infinite | талисман/#page |
| ANM-025 | думает | orbit-8 | 2.2 | infinite | талисман/#page |
| ANM-026 | думает | skew-3 | 1.4 | infinite | талисман/#page |
| ANM-027 | думает | skew-6 | 1.4 | infinite | талисман/#page |
| ANM-028 | думает | dots-0.35 | 1.1 | infinite | талисман/#page |
| ANM-029 | думает | dots-0.6 | 1.1 | infinite | талисман/#page |
| ANM-030 | думает | scan-1.3 | 1.8 | infinite | талисман/#page |
| ANM-031 | думает | scan-1.6 | 1.8 | infinite | талисман/#page |
| ANM-032 | думает | squash-0.9 | 1.2 | infinite | талисман/#page |
| ANM-033 | думает | squash-0.82 | 1.2 | infinite | талисман/#page |
| ANM-034 | думает | twitch-2 | 0.5 | infinite | талисман/#page |
| ANM-035 | думает | twitch-4 | 0.5 | infinite | талисман/#page |
| ANM-036 | думает | flip-2.4 | 2.4 | infinite | талисман/#page |
| ANM-037 | думает | pendulum-10 | 1.6 | infinite | талисман/#page |
| ANM-038 | думает | pendulum-18 | 1.6 | infinite | талисман/#page |
| ANM-039 | думает | blur-1 | 1.6 | infinite | талисман/#page |
| ANM-040 | думает | blur-2 | 1.6 | infinite | талисман/#page |
| ANM-041 | говорит | talk-0.2 | 0.2 | infinite | талисман/#page |
| ANM-042 | говорит | talk-0.3 | 0.3 | infinite | талисман/#page |
| ANM-043 | говорит | talk-0.45 | 0.45 | infinite | талисман/#page |
| ANM-044 | говорит | nod-2 | 0.6 | infinite | талисман/#page |
| ANM-045 | говорит | nod-4 | 0.6 | infinite | талисман/#page |
| ANM-046 | говорит | nod-6 | 0.6 | infinite | талисман/#page |
| ANM-047 | говорит | ripple-8 | 0.9 | infinite | талисман/#page |
| ANM-048 | говорит | ripple-14 | 0.9 | infinite | талисман/#page |
| ANM-049 | говорит | ripple-22 | 0.9 | infinite | талисман/#page |
| ANM-050 | говорит | jaw-0.96 | 0.25 | infinite | талисман/#page |
| ANM-051 | говорит | jaw-0.9 | 0.25 | infinite | талисман/#page |
| ANM-052 | говорит | hop-3 | 0.5 | infinite | талисман/#page |
| ANM-053 | говорит | hop-6 | 0.5 | infinite | талисман/#page |
| ANM-054 | говорит | eq-a | 0.35 | infinite | талисман/#page |
| ANM-055 | говорит | eq-b | 0.5 | infinite | талисман/#page |
| ANM-056 | радость | bounce-10 | 0.9 | 3 | NOXMotion.state("joy") |
| ANM-057 | радость | bounce-16 | 0.9 | 3 | NOXMotion.state("joy") |
| ANM-058 | радость | bounce-24 | 0.9 | 3 | NOXMotion.state("joy") |
| ANM-059 | радость | jump-squash-12 | 0.8 | 3 | NOXMotion.state("joy") |
| ANM-060 | радость | jump-squash-20 | 0.8 | 3 | NOXMotion.state("joy") |
| ANM-061 | радость | jump-squash-30 | 0.8 | 3 | NOXMotion.state("joy") |
| ANM-062 | радость | tada-1.15 | 1 | 1 | NOXMotion.state("joy") |
| ANM-063 | радость | tada-1.3 | 1 | 1 | NOXMotion.state("joy") |
| ANM-064 | радость | jello-8 | 0.9 | 1 | NOXMotion.state("joy") |
| ANM-065 | радость | jello-14 | 0.9 | 1 | NOXMotion.state("joy") |
| ANM-066 | радость | heartbeat-1.1 | 1.1 | 2 | NOXMotion.state("joy") |
| ANM-067 | радость | heartbeat-1.2 | 1.1 | 2 | NOXMotion.state("joy") |
| ANM-068 | радость | spin-pop-0.6 | 0.9 | 1 | NOXMotion.state("joy") |
| ANM-069 | радость | spin-pop-0.8 | 0.9 | 1 | NOXMotion.state("joy") |
| ANM-070 | радость | wiggle-8 | 0.7 | 3 | NOXMotion.state("joy") |
| ANM-071 | радость | wiggle-14 | 0.7 | 3 | NOXMotion.state("joy") |
| ANM-072 | радость | rubber-1.25 | 0.9 | 1 | NOXMotion.state("joy") |
| ANM-073 | радость | rubber-1.4 | 0.9 | 1 | NOXMotion.state("joy") |
| ANM-074 | радость | flash-gold-1.5 | 0.8 | 2 | NOXMotion.state("joy") |
| ANM-075 | радость | flash-gold-2 | 0.8 | 2 | NOXMotion.state("joy") |
| ANM-076 | тревога | shake-6 | 0.5 | 3 | NOXMotion.state("alarm") |
| ANM-077 | тревога | shake-10 | 0.5 | 3 | NOXMotion.state("alarm") |
| ANM-078 | тревога | shake-14 | 0.5 | 3 | NOXMotion.state("alarm") |
| ANM-079 | тревога | headshake-6 | 0.7 | 2 | NOXMotion.state("alarm") |
| ANM-080 | тревога | headshake-12 | 0.7 | 2 | NOXMotion.state("alarm") |
| ANM-081 | тревога | flash-0.2 | 0.6 | infinite | NOXMotion.state("alarm") |
| ANM-082 | тревога | flash-0.4 | 0.6 | infinite | NOXMotion.state("alarm") |
| ANM-083 | тревога | flash-0.6 | 0.6 | infinite | NOXMotion.state("alarm") |
| ANM-084 | тревога | pulse-red-10 | 0.8 | infinite | NOXMotion.state("alarm") |
| ANM-085 | тревога | pulse-red-20 | 0.8 | infinite | NOXMotion.state("alarm") |
| ANM-086 | тревога | vibrate-1 | 0.12 | infinite | NOXMotion.state("alarm") |
| ANM-087 | тревога | vibrate-2 | 0.12 | infinite | NOXMotion.state("alarm") |
| ANM-088 | тревога | heavy-bounce | 0.8 | 2 | NOXMotion.state("alarm") |
| ANM-089 | тревога | wobble-hard-10 | 0.8 | 2 | NOXMotion.state("alarm") |
| ANM-090 | тревога | wobble-hard-16 | 0.8 | 2 | NOXMotion.state("alarm") |
| ANM-091 | переход (вход страницы) | fade-in | 0.45 | 1 | талисман/#page |
| ANM-092 | переход (вход страницы) | fade-up | 0.45 | 1 | талисман/#page |
| ANM-093 | переход (вход страницы) | fade-down | 0.45 | 1 | талисман/#page |
| ANM-094 | переход (вход страницы) | slide-left | 0.45 | 1 | талисман/#page |
| ANM-095 | переход (вход страницы) | slide-right | 0.45 | 1 | талисман/#page |
| ANM-096 | переход (вход страницы) | zoom-in | 0.45 | 1 | талисман/#page |
| ANM-097 | переход (вход страницы) | zoom-out | 0.45 | 1 | талисман/#page |
| ANM-098 | переход (вход страницы) | flip-in | 0.45 | 1 | талисман/#page |
| ANM-099 | переход (вход страницы) | blur-in | 0.45 | 1 | талисман/#page |
| ANM-100 | переход (вход страницы) | rotate-in | 0.45 | 1 | талисман/#page |
