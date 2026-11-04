/* EXPRESS UI navigation catalog. Eight approved physical directions; 10 optional
   graphical worlds are views inside the approved directions, never CoreID. */
export const DIRECTIONS=Object.freeze([
 ["work","РАБОТА"],["intelligence","ИНТЕЛЛЕКТ"],["knowledge","ЗНАНИЯ"],
 ["creative","ТВОРЧЕСТВО"],["people","ЛЮДИ"],["development","РАЗВИТИЕ"],
 ["world","МИР"],["system","СИСТЕМА"]
]);
export const CORE_IDS=Object.freeze(["CONSCIOUSNESS","PERSONA","ATLAS","VOICE","REFLECTION","CORE","NEXUS","FORGE"]);
export const PERSONAS=Object.freeze(["KV","AM","LA","EV","KW"]);
export const PRIMARY=Object.freeze(["CHAT","INSTALL","MODELS","LEARN","REPORTS"]);
const data=[
 ["work","РАБОТА","work","Проекты и задачи","projects~Проекты|architecture~Архитектура|commands~Команды|progress~Прогресс"],
 ["intelligence","ИНТЕЛЛЕКТ","intelligence","Локальный ИИ и исследования","chat~Чат HELION|search~Поиск|fact-atlas~Атлас фактов|browser~Браузер NOX"],
 ["knowledge","ЗНАНИЯ","knowledge","Книги, память, источники","books~Книги|book-shelf~Книжная полка|memory~Память|chat-history~История чата|archive-import~Импорт архива|media-watch-history~История просмотра|persona-memory~Память персон"],
 ["learning","ОБУЧЕНИЕ","development","Саморазвитие и GPU","evolution~Эволюция|study-queue~Очередь обучения|learning-proofs~Доказательства обучения|curriculum~Программа обучения|skill-academy~Академия навыков|study-scheduler~Расписание|weights~Адаптеры и веса|gpu-training~GPU-обучение"],
 ["entertainment","КИНО И МЕДИА","creative","Кинотеатр и субтитры","cinema~Кинотеатр|film-search~Поиск фильмов|movie-source-manager~Источники кино|cinema-player~Проигрыватель|film-subtitles~Субтитры"],
 ["people","ЛЮДИ","people","Персоны и общение","cast~Пять персон|identity-profile~Профиль личности|advanced-traits~Черты|create-persona~Новая персона|reflection~Рефлексия|style~Стиль|style-boundaries~Границы стиля|style-history~История стиля|mail-hub~Почта|messenger-hub~Мессенджеры|calls~Звонки|calls-console~Консоль звонков|voice-studio~Студия голоса|voice-devices~Аудиоустройства|live-translate~Перевод"],
 ["creative","ТВОРЧЕСТВО","creative","Создание контента","creative~Творческая студия|site-factory~Конструктор сайтов"],
 ["business","БИЗНЕС","work","Маркетинг и календарь","meetings-calendar~Календарь|marketing~Маркетинг"],
 ["world","МИР","world","Пространства и устройства","spaces~Пространства|smart-home~Умный дом"],
 ["pc","СИСТЕМА И ПК","system","Модели, безопасность, ресурсы","system~Система NOX|core-status~Состояние ядер|model-library~Каталог моделей|model-load~Установленные модели|settings~Настройки|voice-command-router~Голосовые команды|pc-control~Управление ПК|devices~Устройства|security~Безопасность|backup~Резервные копии|updates~Обновления|mini~Мини-окно|connectors-hub~Интеграции|provider-status~Провайдеры|global-notifications-inbox~Уведомления"]
];
export const WORLDS=Object.freeze(data.map(([id,title,section,description,routes],i)=>Object.freeze({
 id,title,section,description,index:i,
 routes:Object.freeze(routes.split("|").map(value=>{const [id,label]=value.split("~");return Object.freeze({id,label});}))
})));
export const ROUTE_COUNT=WORLDS.reduce((n,w)=>n+w.routes.length,0);
export function getWorld(id){return WORLDS.find(w=>w.id===id)||null;}
export function getRoute(id){for(const w of WORLDS){const route=w.routes.find(r=>r.id===id);if(route)return {...route,world:w};}return null;}
