/* Каталог планет NOX WOW (общий для фона и настроек). tex: кандидаты файлов в vendor/nox-planets/ (сначала 2k SSS с S1, потом уменьшенные из сборки); proc: запасная процедурная палитра. */
/* tex: кандидаты (сначала 2k Solar System Scope с S1, потом уменьшенные из сборки); proc: запасная процедурная палитра */
export const PLANETS = [
  { id: 'none', name: 'Космос', note: 'только туманность и звёзды' },
  { id: 'mercury', name: 'Меркурий', tex: ['2k_mercury.jpg'], proc: { base: [.42, .40, .38], hi: [.7, .67, .62], crater: 1 }, atm: [.5, .5, .55], atmK: .15 },
  { id: 'venus', name: 'Венера', tex: ['2k_venus_surface.jpg'], proc: { base: [.72, .5, .25], hi: [.97, .88, .66], band: .3 }, atm: [1, .75, .4], atmK: .9 },
  { id: 'earth', name: 'Земля', tex: ['2k_earth_daymap.jpg', 'earth_daymap.jpg'], proc: { base: [.05, .18, .4], hi: [.2, .5, .25], land: 1 }, atm: [.3, .55, 1], atmK: 1 },
  { id: 'moon', name: 'Луна', tex: ['2k_moon.jpg', 'moon.jpg'], proc: { base: [.38, .38, .39], hi: [.72, .72, .7], crater: 1 }, atm: [.6, .6, .62], atmK: .1 },
  { id: 'mars', name: 'Марс', tex: ['2k_mars.jpg'], proc: { base: [.45, .2, .1], hi: [.82, .45, .24], crater: .5 }, atm: [1, .5, .3], atmK: .5 },
  { id: 'jupiter', name: 'Юпитер', tex: ['2k_jupiter.jpg'], proc: { base: [.62, .45, .32], hi: [.92, .84, .72], band: 1 }, atm: [1, .8, .6], atmK: .6 },
  { id: 'saturn', name: 'Сатурн', tex: ['2k_saturn.jpg'], ring: '2k_saturn_ring_alpha.png', proc: { base: [.72, .6, .4], hi: [.93, .86, .68], band: .8 }, atm: [1, .85, .55], atmK: .5 },
  { id: 'uranus', name: 'Уран', tex: ['2k_uranus.jpg'], proc: { base: [.5, .8, .85], hi: [.7, .92, .95], band: .15 }, atm: [.5, .9, .95], atmK: .8 },
  { id: 'neptune', name: 'Нептун', tex: ['2k_neptune.jpg'], proc: { base: [.12, .25, .75], hi: [.35, .5, .95], band: .35 }, atm: [.3, .5, 1], atmK: .9 }
];
export const byId = (id) => PLANETS.find((p) => p.id === id) || PLANETS[3];
