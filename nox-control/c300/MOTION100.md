# MOTION100: 100 анимаций NOX (K5)

Источник (K6, реальный): настоящие библиотеки из npm registry, лежат в site/vendor/: animate.css 4.1.1 (MIT, vendor/animate.css/animate.min.css, 72 КБ), hover.css 2.3.2 (бесплатно для личного/open-source использования по MIT; для коммерческого проекта нужна платная лицензия Ian Lunn, в npm-пакете поле license пустое; vendor/hover.css/hover-min.css, 95 КБ), magic.css 1.4.8 (MIT, vendor/magic.css/magic.min.css, 34 КБ), @formkit/auto-animate 0.11.0 (MIT, vendor/auto-animate/index.mjs, 37 КБ). GSAP (vendor/gsap) остаётся исполнителем для пресетов без аналога.
Лицензия: код библиотек остаётся под их лицензиями (см. LICENSE в vendor/<имя>/). Собственные пресеты NOX без аналога (float/glow/hue/spin/orbit/dots/scan/ripple/eq/vibrate-красный и др.) оставлены на GSAP и CSS .anm-NNN из K5. Подключение: site/nox-k6-motionlib.js (до nox-k5-motion100.js) перехватывает NOXMotion.play и играет классы библиотек (animate__*, magictime, keyframes hover.css); AutoAnimate (NOXMotionLib.autoAnimate) навешен на #msgs и [data-auto-animate].
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


## K6: соответствие библиотекам

С классами/keyframes библиотек: 67 из 100; остальные 33 остались собственными (GSAP/CSS K5), т.к. прямого аналога нет.

| ANM | Библиотека | Класс/keyframes |
|---|---|---|
| ANM-001 | hover.css | hvr-bob |
| ANM-002 | hover.css | hvr-bob |
| ANM-003 | hover.css | hvr-bob |
| ANM-004 | hover.css | hvr-bob |
| ANM-005 | animate.css | pulse |
| ANM-006 | animate.css | pulse |
| ANM-007 | animate.css | pulse |
| ANM-008 | animate.css | swing |
| ANM-009 | animate.css | swing |
| ANM-010 | animate.css | swing |
| ANM-014 | hover.css | hvr-wobble-horizontal |
| ANM-015 | hover.css | hvr-wobble-horizontal |
| ANM-034 | hover.css | hvr-buzz |
| ANM-035 | hover.css | hvr-buzz |
| ANM-036 | animate.css | flip |
| ANM-037 | animate.css | swing |
| ANM-038 | animate.css | swing |
| ANM-044 | hover.css | hvr-hang |
| ANM-045 | hover.css | hvr-hang |
| ANM-046 | hover.css | hvr-hang |
| ANM-052 | animate.css | bounce |
| ANM-053 | animate.css | bounce |
| ANM-056 | animate.css | bounce |
| ANM-057 | animate.css | bounce |
| ANM-058 | animate.css | bounce |
| ANM-059 | animate.css | bounceIn |
| ANM-060 | animate.css | bounceIn |
| ANM-061 | animate.css | bounceIn |
| ANM-062 | animate.css | tada |
| ANM-063 | animate.css | tada |
| ANM-064 | animate.css | jello |
| ANM-065 | animate.css | jello |
| ANM-066 | animate.css | heartBeat |
| ANM-067 | animate.css | heartBeat |
| ANM-068 | magic.css | puffIn |
| ANM-069 | magic.css | puffIn |
| ANM-070 | animate.css | wobble |
| ANM-071 | animate.css | wobble |
| ANM-072 | animate.css | rubberBand |
| ANM-073 | animate.css | rubberBand |
| ANM-074 | animate.css | flash |
| ANM-075 | animate.css | flash |
| ANM-076 | animate.css | shakeX |
| ANM-077 | animate.css | shakeX |
| ANM-078 | animate.css | shakeX |
| ANM-079 | animate.css | headShake |
| ANM-080 | animate.css | headShake |
| ANM-081 | animate.css | flash |
| ANM-082 | animate.css | flash |
| ANM-083 | animate.css | flash |
| ANM-084 | animate.css | pulse |
| ANM-085 | animate.css | pulse |
| ANM-086 | hover.css | hvr-buzz |
| ANM-087 | hover.css | hvr-buzz |
| ANM-088 | animate.css | bounce |
| ANM-089 | animate.css | wobble |
| ANM-090 | animate.css | wobble |
| ANM-091 | animate.css | fadeIn |
| ANM-092 | animate.css | fadeInUp |
| ANM-093 | animate.css | fadeInDown |
| ANM-094 | animate.css | fadeInRight |
| ANM-095 | animate.css | fadeInLeft |
| ANM-096 | animate.css | zoomIn |
| ANM-097 | magic.css | puffIn |
| ANM-098 | animate.css | flipInY |
| ANM-099 | magic.css | vanishIn |
| ANM-100 | animate.css | rotateIn |
