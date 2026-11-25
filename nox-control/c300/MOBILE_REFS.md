# MOBILE_REFS: мобильные референсы для NOX HELION (исполнитель M, 2026-11-25)
Источники: топ-100 приложений/систем (список ниже, ссылки на официальные страницы; поиск подтвердил Apple HIG/WWDC25, Material 3 Expressive, обзоры суперприложений vc.ru/Miquido/Netguru). Приоритет: P0 обязательно, P1 важно, P2 по возможности.
Опорные ссылки: [HIG tab bars](https://developer.apple.com/design/human-interface-guidelines/tab-bars) · [WWDC25 Liquid Glass](https://developer.apple.com/videos/play/wwdc2025/284/) · [M3 Expressive navigation](https://9to5google.com/2025/05/14/material-3-expressive-navigation/) · [M3 toolbars](https://9to5google.com/2025/05/18/material-3-expressive-toolbars/) · [Super apps UX (Miquido)](https://www.miquido.com/blog/super-app-design/) · [Яндекс Go](https://vc.ru/152319-super-app-yandeks-go-uspeh-ili-proval) · [Grab vs RU](https://vc.ru/services/102327-chto-vnutri-superprilozheniya-grab-sravnivaem-s-rossiiskimi-analogami)

## Топ-20 паттернов для NOX
| # | Паттерн | Откуда | Решение в NOX | Приоритет |
|---|---|---|---|---|
| 1 | Нижний таб-бар 5 пунктов + «Ещё» | iOS, Яндекс Go, Т-Банк, Spotify | #nox-m-tabbar вместо дока | P0 |
| 2 | Сетка сервисов «Ещё» в шторке | Яндекс Go, Grab, Alipay, Kaspi | шторка с плитками из nav.json | P0 |
| 3 | Единая плавающая кнопка ИИ над таб-баром | Алиса, Gemini, Copilot, Samsung | сведены mini-chat/«Спросить»/«NOX,»/«?» | P0 |
| 4 | Модалки как нижние шторки | iOS sheets, M3, Maps | dialog/sl-dialog/модалки -> sheet | P0 |
| 5 | safe-area-inset | iOS/Android edge-to-edge | env(safe-area-inset-*) у шапки/таб-бара | P0 |
| 6 | Цели не меньше 44 px | HIG, M3 (48dp) | min-height/width 44 | P0 |
| 7 | Шрифт не меньше 14 px | M3, HIG Dynamic Type | body/inputs 14+, без zoom iOS | P0 |
| 8 | Свайп от края «назад» | iOS, Telegram, VK | touch edge-swipe -> history.back | P0 |
| 9 | Pull-to-refresh | Gmail, Instagram, Chrome | на страницах с обновлением данных | P1 |
| 10 | Закрытие шторки свайпом вниз + ручка | iOS, M3, Maps | drag-handle | P0 |
| 11 | Haptics | iOS, Revolut, Things | ios-haptics на табы/шторки | P1 |
| 12 | Поиск сверху | Яндекс, Perplexity, Arc | кнопка поиска в шапке -> nox-cmd | P1 |
| 13 | Кнопка «назад» в шапке | iOS, Settings | стрелка в шапке на внутренних страницах | P1 |
| 14 | Стеклянные панели | Liquid Glass, HyperOS | backdrop-filter на таб-баре/шторках | P1 |
| 15 | Карусели историй | Т-Банк, Instagram, Sber | Swiper на главной/новостях | P2 |
| 16 | Горизонтальные чипы-фильтры | Airbnb, Spotify | прокрутка чипов без page-overflow | P1 |
| 17 | Крупные карточки, один столбец | Revolut, Monzo | grid -> 1 колонка <=480 | P0 |
| 18 | Скрытие таб-бара при вводе | iOS, Telegram | при фокусе input с клавиатурой | P1 |
| 19 | Тёмная тема по умолчанию | ChatGPT, Spotify | уже есть | P2 |
| 20 | Жест «потянуть» мини-плеера/шторки | Spotify, Apple Music | шторка на 2 высоты | P2 |

## Все референсы (приложение | паттерн | ссылка | страница NOX | модуль | приоритет)
| Приложение | Паттерн | Ссылка | Страница NOX | Модуль | Приоритет |
|---|---|---|---|---|---|
| Яндекс Go | сервисная сетка «всё в одном» | https://go.yandex/ | Ещё (шторка) | nox-m-mobile.js: сетка сервисов | P0 |
| Яндекс Go | нижний таб-бар | https://go.yandex/ | все страницы | nox-m-mobile.js: таб-бар | P0 |
| Яндекс Go | поиск сверху | https://go.yandex/ | index, chat, knowledge | поиск сверху (nox-cmd) | P1 |
| Алиса (Яндекс) | плавающая кнопка ИИ | https://alice.yandex.ru/ | все | nox-m-mobile.js: единая кнопка ИИ | P0 |
| Алиса (Яндекс) | нижняя шторка | https://alice.yandex.ru/ | все модалки | nox-m-mobile.js: sheet | P0 |
| Яндекс (Браузер/Старт) | поиск сверху | https://yandex.ru/mobile | index, chat, knowledge | поиск сверху (nox-cmd) | P1 |
| Яндекс (Браузер/Старт) | карусель историй | https://yandex.ru/mobile | index, news, glance | Swiper/embla карусель | P2 |
| Яндекс Музыка | нижний таб-бар | https://music.yandex.ru/ | все страницы | nox-m-mobile.js: таб-бар | P0 |
| Яндекс Музыка | нижняя шторка | https://music.yandex.ru/ | все модалки | nox-m-mobile.js: sheet | P0 |
| Яндекс Карты | нижняя шторка | https://yandex.ru/maps | все модалки | nox-m-mobile.js: sheet | P0 |
| Яндекс Карты | поиск сверху | https://yandex.ru/maps | index, chat, knowledge | поиск сверху (nox-cmd) | P1 |
| Сбербанк Онлайн | нижний таб-бар | https://www.sberbank.ru/ru/person/dist_services/inet | все страницы | nox-m-mobile.js: таб-бар | P0 |
| Сбербанк Онлайн | сервисная сетка «всё в одном» | https://www.sberbank.ru/ru/person/dist_services/inet | Ещё (шторка) | nox-m-mobile.js: сетка сервисов | P0 |
| Сбербанк Онлайн | карусель историй | https://www.sberbank.ru/ru/person/dist_services/inet | index, news, glance | Swiper/embla карусель | P2 |
| GigaChat | плавающая кнопка ИИ | https://giga.chat/ | все | nox-m-mobile.js: единая кнопка ИИ | P0 |
| GigaChat | нижняя шторка | https://giga.chat/ | все модалки | nox-m-mobile.js: sheet | P0 |
| Т-Банк | нижний таб-бар | https://www.tbank.ru/mobile-apps/ | все страницы | nox-m-mobile.js: таб-бар | P0 |
| Т-Банк | карусель историй | https://www.tbank.ru/mobile-apps/ | index, news, glance | Swiper/embla карусель | P2 |
| Т-Банк | сервисная сетка «всё в одном» | https://www.tbank.ru/mobile-apps/ | Ещё (шторка) | nox-m-mobile.js: сетка сервисов | P0 |
| Kaspi.kz | сервисная сетка «всё в одном» | https://kaspi.kz/ | Ещё (шторка) | nox-m-mobile.js: сетка сервисов | P0 |
| Kaspi.kz | нижний таб-бар | https://kaspi.kz/ | все страницы | nox-m-mobile.js: таб-бар | P0 |
| Kaspi.kz | поиск сверху | https://kaspi.kz/ | index, chat, knowledge | поиск сверху (nox-cmd) | P1 |
| ВТБ Онлайн | нижний таб-бар | https://www.vtb.ru/personal/mobilnyj-bank/ | все страницы | nox-m-mobile.js: таб-бар | P0 |
| ВТБ Онлайн | карусель историй | https://www.vtb.ru/personal/mobilnyj-bank/ | index, news, glance | Swiper/embla карусель | P2 |
| Альфа-Банк | нижний таб-бар | https://alfabank.ru/mobile/ | все страницы | nox-m-mobile.js: таб-бар | P0 |
| Альфа-Банк | карусель историй | https://alfabank.ru/mobile/ | index, news, glance | Swiper/embla карусель | P2 |
| VK | нижний таб-бар | https://vk.com/apps | все страницы | nox-m-mobile.js: таб-бар | P0 |
| VK | карусель историй | https://vk.com/apps | index, news, glance | Swiper/embla карусель | P2 |
| VK | свайп-жесты/назад | https://vk.com/apps | все (назад) | nox-m-mobile.js: edge-swipe back | P0 |
| VK Мессенджер/Max | нижний таб-бар | https://max.ru/ | все страницы | nox-m-mobile.js: таб-бар | P0 |
| VK Мессенджер/Max | нижняя шторка | https://max.ru/ | все модалки | nox-m-mobile.js: sheet | P0 |
| VK Мессенджер/Max | свайп-жесты/назад | https://max.ru/ | все (назад) | nox-m-mobile.js: edge-swipe back | P0 |
| Telegram | нижний таб-бар | https://telegram.org/apps | все страницы | nox-m-mobile.js: таб-бар | P0 |
| Telegram | свайп-жесты/назад | https://telegram.org/apps | все (назад) | nox-m-mobile.js: edge-swipe back | P0 |
| Telegram | нижняя шторка | https://telegram.org/apps | все модалки | nox-m-mobile.js: sheet | P0 |
| Telegram | поиск сверху | https://telegram.org/apps | index, chat, knowledge | поиск сверху (nox-cmd) | P1 |
| WeChat | нижний таб-бар | https://www.wechat.com/ | все страницы | nox-m-mobile.js: таб-бар | P0 |
| WeChat | сервисная сетка «всё в одном» | https://www.wechat.com/ | Ещё (шторка) | nox-m-mobile.js: сетка сервисов | P0 |
| WeChat | поиск сверху | https://www.wechat.com/ | index, chat, knowledge | поиск сверху (nox-cmd) | P1 |
| Alipay | сервисная сетка «всё в одном» | https://global.alipay.com/ | Ещё (шторка) | nox-m-mobile.js: сетка сервисов | P0 |
| Alipay | поиск сверху | https://global.alipay.com/ | index, chat, knowledge | поиск сверху (nox-cmd) | P1 |
| Alipay | нижний таб-бар | https://global.alipay.com/ | все страницы | nox-m-mobile.js: таб-бар | P0 |
| Grab | сервисная сетка «всё в одном» | https://www.grab.com/sg/ | Ещё (шторка) | nox-m-mobile.js: сетка сервисов | P0 |
| Grab | нижний таб-бар | https://www.grab.com/sg/ | все страницы | nox-m-mobile.js: таб-бар | P0 |
| Grab | нижняя шторка | https://www.grab.com/sg/ | все модалки | nox-m-mobile.js: sheet | P0 |
| Gojek | сервисная сетка «всё в одном» | https://www.gojek.com/ | Ещё (шторка) | nox-m-mobile.js: сетка сервисов | P0 |
| Gojek | нижний таб-бар | https://www.gojek.com/ | все страницы | nox-m-mobile.js: таб-бар | P0 |
| Revolut | нижний таб-бар | https://www.revolut.com/ | все страницы | nox-m-mobile.js: таб-бар | P0 |
| Revolut | нижняя шторка | https://www.revolut.com/ | все модалки | nox-m-mobile.js: sheet | P0 |
| Revolut | карусель историй | https://www.revolut.com/ | index, news, glance | Swiper/embla карусель | P2 |
| Revolut | haptics | https://www.revolut.com/ | все | ios-haptics | P1 |
| Monzo | нижний таб-бар | https://monzo.com/ | все страницы | nox-m-mobile.js: таб-бар | P0 |
| Monzo | нижняя шторка | https://monzo.com/ | все модалки | nox-m-mobile.js: sheet | P0 |
| Monzo | haptics | https://monzo.com/ | все | ios-haptics | P1 |
| Apple iOS 26 Liquid Glass | стекло/Liquid Glass | https://www.apple.com/newsroom/2025/06/apple-introduces-a-delightful-and-elegant-new-software-design/ | док, шапка, шторки | backdrop-filter стекло | P1 |
| Apple iOS 26 Liquid Glass | нижний таб-бар | https://www.apple.com/newsroom/2025/06/apple-introduces-a-delightful-and-elegant-new-software-design/ | все страницы | nox-m-mobile.js: таб-бар | P0 |
| Apple iOS 26 Liquid Glass | нижняя шторка | https://www.apple.com/newsroom/2025/06/apple-introduces-a-delightful-and-elegant-new-software-design/ | все модалки | nox-m-mobile.js: sheet | P0 |
| Apple iOS 26 Liquid Glass | haptics | https://www.apple.com/newsroom/2025/06/apple-introduces-a-delightful-and-elegant-new-software-design/ | все | ios-haptics | P1 |
| Apple HIG Tab bars | нижний таб-бар | https://developer.apple.com/design/human-interface-guidelines/tab-bars | все страницы | nox-m-mobile.js: таб-бар | P0 |
| Apple HIG Tab bars | safe-area | https://developer.apple.com/design/human-interface-guidelines/tab-bars | все | nox-m-mobile.css: safe-area | P0 |
| Apple HIG Tab bars | крупные цели | https://developer.apple.com/design/human-interface-guidelines/tab-bars | все | nox-m-mobile.css: 44px | P0 |
| Apple HIG Sheets | нижняя шторка | https://developer.apple.com/design/human-interface-guidelines/sheets | все модалки | nox-m-mobile.js: sheet | P0 |
| Apple HIG Sheets | свайп-жесты/назад | https://developer.apple.com/design/human-interface-guidelines/sheets | все (назад) | nox-m-mobile.js: edge-swipe back | P0 |
| Apple Siri/Apple Intelligence | плавающая кнопка ИИ | https://www.apple.com/apple-intelligence/ | все | nox-m-mobile.js: единая кнопка ИИ | P0 |
| Apple Siri/Apple Intelligence | нижняя шторка | https://www.apple.com/apple-intelligence/ | все модалки | nox-m-mobile.js: sheet | P0 |
| Apple Maps | нижняя шторка | https://www.apple.com/ios/maps/ | все модалки | nox-m-mobile.js: sheet | P0 |
| Apple Maps | поиск сверху | https://www.apple.com/ios/maps/ | index, chat, knowledge | поиск сверху (nox-cmd) | P1 |
| Apple Music | нижний таб-бар | https://www.apple.com/apple-music/ | все страницы | nox-m-mobile.js: таб-бар | P0 |
| Apple Music | нижняя шторка | https://www.apple.com/apple-music/ | все модалки | nox-m-mobile.js: sheet | P0 |
| Apple Music | тёмная тема | https://www.apple.com/apple-music/ | все | уже тёмное стекло | P2 |
| Apple Wallet | нижняя шторка | https://www.apple.com/wallet/ | все модалки | nox-m-mobile.js: sheet | P0 |
| Apple Wallet | карусель историй | https://www.apple.com/wallet/ | index, news, glance | Swiper/embla карусель | P2 |
| Apple Safari iOS 26 | нижний таб-бар | https://www.apple.com/safari/ | все страницы | nox-m-mobile.js: таб-бар | P0 |
| Apple Safari iOS 26 | поиск сверху | https://www.apple.com/safari/ | index, chat, knowledge | поиск сверху (nox-cmd) | P1 |
| Apple Safari iOS 26 | стекло/Liquid Glass | https://www.apple.com/safari/ | док, шапка, шторки | backdrop-filter стекло | P1 |
| Apple Messages | свайп-жесты/назад | https://support.apple.com/messages | все (назад) | nox-m-mobile.js: edge-swipe back | P0 |
| Apple Messages | поиск сверху | https://support.apple.com/messages | index, chat, knowledge | поиск сверху (nox-cmd) | P1 |
| Apple Messages | haptics | https://support.apple.com/messages | все | ios-haptics | P1 |
| Apple Settings | кнопка «назад» | https://support.apple.com/guide/iphone/welcome/ios | внутренние страницы | кнопка «назад» в шапке | P1 |
| Apple Settings | поиск сверху | https://support.apple.com/guide/iphone/welcome/ios | index, chat, knowledge | поиск сверху (nox-cmd) | P1 |
| Apple Settings | сервисная сетка «всё в одном» | https://support.apple.com/guide/iphone/welcome/ios | Ещё (шторка) | nox-m-mobile.js: сетка сервисов | P0 |
| Google Gemini app | плавающая кнопка ИИ | https://gemini.google/overview/gemini-app/ | все | nox-m-mobile.js: единая кнопка ИИ | P0 |
| Google Gemini app | нижняя шторка | https://gemini.google/overview/gemini-app/ | все модалки | nox-m-mobile.js: sheet | P0 |
| Google Gemini app | тёмная тема | https://gemini.google/overview/gemini-app/ | все | уже тёмное стекло | P2 |
| Material 3 Expressive | нижний таб-бар | https://m3.material.io/ | все страницы | nox-m-mobile.js: таб-бар | P0 |
| Material 3 Expressive | нижняя шторка | https://m3.material.io/ | все модалки | nox-m-mobile.js: sheet | P0 |
| Material 3 Expressive | haptics | https://m3.material.io/ | все | ios-haptics | P1 |
| Material 3 Expressive | крупные цели | https://m3.material.io/ | все | nox-m-mobile.css: 44px | P0 |
| Material 3 Navigation bar | нижний таб-бар | https://m3.material.io/components/navigation-bar/overview | все страницы | nox-m-mobile.js: таб-бар | P0 |
| Material 3 Navigation bar | крупные цели | https://m3.material.io/components/navigation-bar/overview | все | nox-m-mobile.css: 44px | P0 |
| Material 3 Bottom sheets | нижняя шторка | https://m3.material.io/components/bottom-sheets/overview | все модалки | nox-m-mobile.js: sheet | P0 |
| Material 3 Bottom sheets | свайп-жесты/назад | https://m3.material.io/components/bottom-sheets/overview | все (назад) | nox-m-mobile.js: edge-swipe back | P0 |
| Google Pixel launcher/Circle to Search | поиск сверху | https://search.google/ways-to-search/circle-to-search/ | index, chat, knowledge | поиск сверху (nox-cmd) | P1 |
| Google Pixel launcher/Circle to Search | плавающая кнопка ИИ | https://search.google/ways-to-search/circle-to-search/ | все | nox-m-mobile.js: единая кнопка ИИ | P0 |
| Google Maps | нижняя шторка | https://www.google.com/maps | все модалки | nox-m-mobile.js: sheet | P0 |
| Google Maps | поиск сверху | https://www.google.com/maps | index, chat, knowledge | поиск сверху (nox-cmd) | P1 |
| Google Maps | нижний таб-бар | https://www.google.com/maps | все страницы | nox-m-mobile.js: таб-бар | P0 |
| Google Photos | нижний таб-бар | https://photos.google.com/ | все страницы | nox-m-mobile.js: таб-бар | P0 |
| Google Photos | свайп-жесты/назад | https://photos.google.com/ | все (назад) | nox-m-mobile.js: edge-swipe back | P0 |
| Google Photos | поиск сверху | https://photos.google.com/ | index, chat, knowledge | поиск сверху (nox-cmd) | P1 |
| Gmail | нижний таб-бар | https://workspace.google.com/products/gmail/ | все страницы | nox-m-mobile.js: таб-бар | P0 |
| Gmail | свайп-жесты/назад | https://workspace.google.com/products/gmail/ | все (назад) | nox-m-mobile.js: edge-swipe back | P0 |
| Gmail | pull-to-refresh | https://workspace.google.com/products/gmail/ | news, glance, dispatcher, downloads | nox-m-mobile.js: pull-to-refresh | P1 |
| Gmail | плавающая кнопка ИИ | https://workspace.google.com/products/gmail/ | все | nox-m-mobile.js: единая кнопка ИИ | P0 |
| YouTube | нижний таб-бар | https://www.youtube.com/ | все страницы | nox-m-mobile.js: таб-бар | P0 |
| YouTube | нижняя шторка | https://www.youtube.com/ | все модалки | nox-m-mobile.js: sheet | P0 |
| YouTube | свайп-жесты/назад | https://www.youtube.com/ | все (назад) | nox-m-mobile.js: edge-swipe back | P0 |
| YouTube | карусель историй | https://www.youtube.com/ | index, news, glance | Swiper/embla карусель | P2 |
| YouTube Music | нижний таб-бар | https://music.youtube.com/ | все страницы | nox-m-mobile.js: таб-бар | P0 |
| YouTube Music | нижняя шторка | https://music.youtube.com/ | все модалки | nox-m-mobile.js: sheet | P0 |
| YouTube Music | тёмная тема | https://music.youtube.com/ | все | уже тёмное стекло | P2 |
| Google Home | нижний таб-бар | https://home.google.com/ | все страницы | nox-m-mobile.js: таб-бар | P0 |
| Google Home | сервисная сетка «всё в одном» | https://home.google.com/ | Ещё (шторка) | nox-m-mobile.js: сетка сервисов | P0 |
| Google Home | нижняя шторка | https://home.google.com/ | все модалки | nox-m-mobile.js: sheet | P0 |
| Google Drive | нижний таб-бар | https://www.google.com/drive/ | все страницы | nox-m-mobile.js: таб-бар | P0 |
| Google Drive | плавающая кнопка ИИ | https://www.google.com/drive/ | все | nox-m-mobile.js: единая кнопка ИИ | P0 |
| Google Drive | поиск сверху | https://www.google.com/drive/ | index, chat, knowledge | поиск сверху (nox-cmd) | P1 |
| Google Messages | нижний таб-бар | https://messages.google.com/ | все страницы | nox-m-mobile.js: таб-бар | P0 |
| Google Messages | плавающая кнопка ИИ | https://messages.google.com/ | все | nox-m-mobile.js: единая кнопка ИИ | P0 |
| Google Messages | свайп-жесты/назад | https://messages.google.com/ | все (назад) | nox-m-mobile.js: edge-swipe back | P0 |
| Google Wallet | нижняя шторка | https://wallet.google/ | все модалки | nox-m-mobile.js: sheet | P0 |
| Google Wallet | карусель историй | https://wallet.google/ | index, news, glance | Swiper/embla карусель | P2 |
| Chrome Android | нижний таб-бар | https://www.google.com/chrome/ | все страницы | nox-m-mobile.js: таб-бар | P0 |
| Chrome Android | нижняя шторка | https://www.google.com/chrome/ | все модалки | nox-m-mobile.js: sheet | P0 |
| Chrome Android | pull-to-refresh | https://www.google.com/chrome/ | news, glance, dispatcher, downloads | nox-m-mobile.js: pull-to-refresh | P1 |
| Chrome Android | поиск сверху | https://www.google.com/chrome/ | index, chat, knowledge | поиск сверху (nox-cmd) | P1 |
| Samsung One UI 7/8 | крупные цели | https://www.samsung.com/global/one-ui/ | все | nox-m-mobile.css: 44px | P0 |
| Samsung One UI 7/8 | кнопка «назад» | https://www.samsung.com/global/one-ui/ | внутренние страницы | кнопка «назад» в шапке | P1 |
| Samsung One UI 7/8 | нижняя шторка | https://www.samsung.com/global/one-ui/ | все модалки | nox-m-mobile.js: sheet | P0 |
| Samsung One UI 7/8 | safe-area | https://www.samsung.com/global/one-ui/ | все | nox-m-mobile.css: safe-area | P0 |
| Samsung Now Bar | плавающая кнопка ИИ | https://www.samsung.com/us/support/answer/ANS10002013/ | все | nox-m-mobile.js: единая кнопка ИИ | P0 |
| Samsung Now Bar | стекло/Liquid Glass | https://www.samsung.com/us/support/answer/ANS10002013/ | док, шапка, шторки | backdrop-filter стекло | P1 |
| Samsung Internet | нижний таб-бар | https://www.samsung.com/us/support/owners/app/samsung-internet | все страницы | nox-m-mobile.js: таб-бар | P0 |
| Samsung Internet | нижняя шторка | https://www.samsung.com/us/support/owners/app/samsung-internet | все модалки | nox-m-mobile.js: sheet | P0 |
| Samsung Internet | поиск сверху | https://www.samsung.com/us/support/owners/app/samsung-internet | index, chat, knowledge | поиск сверху (nox-cmd) | P1 |
| Samsung Galaxy AI (Bixby) | плавающая кнопка ИИ | https://www.samsung.com/global/galaxy/galaxy-ai/ | все | nox-m-mobile.js: единая кнопка ИИ | P0 |
| Samsung Galaxy AI (Bixby) | нижняя шторка | https://www.samsung.com/global/galaxy/galaxy-ai/ | все модалки | nox-m-mobile.js: sheet | P0 |
| Xiaomi HyperOS | стекло/Liquid Glass | https://hyperos.mi.com/ | док, шапка, шторки | backdrop-filter стекло | P1 |
| Xiaomi HyperOS | сервисная сетка «всё в одном» | https://hyperos.mi.com/ | Ещё (шторка) | nox-m-mobile.js: сетка сервисов | P0 |
| Xiaomi HyperOS | нижняя шторка | https://hyperos.mi.com/ | все модалки | nox-m-mobile.js: sheet | P0 |
| Microsoft Copilot app | плавающая кнопка ИИ | https://copilot.microsoft.com/ | все | nox-m-mobile.js: единая кнопка ИИ | P0 |
| Microsoft Copilot app | нижняя шторка | https://copilot.microsoft.com/ | все модалки | nox-m-mobile.js: sheet | P0 |
| Microsoft Copilot app | тёмная тема | https://copilot.microsoft.com/ | все | уже тёмное стекло | P2 |
| Microsoft Edge mobile | нижний таб-бар | https://www.microsoft.com/edge/mobile | все страницы | nox-m-mobile.js: таб-бар | P0 |
| Microsoft Edge mobile | поиск сверху | https://www.microsoft.com/edge/mobile | index, chat, knowledge | поиск сверху (nox-cmd) | P1 |
| Microsoft Edge mobile | нижняя шторка | https://www.microsoft.com/edge/mobile | все модалки | nox-m-mobile.js: sheet | P0 |
| Microsoft Teams | нижний таб-бар | https://www.microsoft.com/microsoft-teams/ | все страницы | nox-m-mobile.js: таб-бар | P0 |
| Microsoft Teams | свайп-жесты/назад | https://www.microsoft.com/microsoft-teams/ | все (назад) | nox-m-mobile.js: edge-swipe back | P0 |
| Microsoft Teams | поиск сверху | https://www.microsoft.com/microsoft-teams/ | index, chat, knowledge | поиск сверху (nox-cmd) | P1 |
| Microsoft Outlook | нижний таб-бар | https://outlook.office.com/ | все страницы | nox-m-mobile.js: таб-бар | P0 |
| Microsoft Outlook | свайп-жесты/назад | https://outlook.office.com/ | все (назад) | nox-m-mobile.js: edge-swipe back | P0 |
| Microsoft Outlook | pull-to-refresh | https://outlook.office.com/ | news, glance, dispatcher, downloads | nox-m-mobile.js: pull-to-refresh | P1 |
| Microsoft 365 app | нижний таб-бар | https://www.microsoft.com/microsoft-365/mobile | все страницы | nox-m-mobile.js: таб-бар | P0 |
| Microsoft 365 app | сервисная сетка «всё в одном» | https://www.microsoft.com/microsoft-365/mobile | Ещё (шторка) | nox-m-mobile.js: сетка сервисов | P0 |
| ChatGPT app | плавающая кнопка ИИ | https://openai.com/chatgpt/download/ | все | nox-m-mobile.js: единая кнопка ИИ | P0 |
| ChatGPT app | нижняя шторка | https://openai.com/chatgpt/download/ | все модалки | nox-m-mobile.js: sheet | P0 |
| ChatGPT app | поиск сверху | https://openai.com/chatgpt/download/ | index, chat, knowledge | поиск сверху (nox-cmd) | P1 |
| ChatGPT app | тёмная тема | https://openai.com/chatgpt/download/ | все | уже тёмное стекло | P2 |
| ChatGPT app | haptics | https://openai.com/chatgpt/download/ | все | ios-haptics | P1 |
| Claude app | нижняя шторка | https://claude.ai/download | все модалки | nox-m-mobile.js: sheet | P0 |
| Claude app | тёмная тема | https://claude.ai/download | все | уже тёмное стекло | P2 |
| Claude app | поиск сверху | https://claude.ai/download | index, chat, knowledge | поиск сверху (nox-cmd) | P1 |
| Claude app | haptics | https://claude.ai/download | все | ios-haptics | P1 |
| Perplexity app | поиск сверху | https://www.perplexity.ai/ | index, chat, knowledge | поиск сверху (nox-cmd) | P1 |
| Perplexity app | нижний таб-бар | https://www.perplexity.ai/ | все страницы | nox-m-mobile.js: таб-бар | P0 |
| Perplexity app | нижняя шторка | https://www.perplexity.ai/ | все модалки | nox-m-mobile.js: sheet | P0 |
| Arc Search | поиск сверху | https://arc.net/ | index, chat, knowledge | поиск сверху (nox-cmd) | P1 |
| Arc Search | свайп-жесты/назад | https://arc.net/ | все (назад) | nox-m-mobile.js: edge-swipe back | P0 |
| Arc Search | haptics | https://arc.net/ | все | ios-haptics | P1 |
| Grok app | плавающая кнопка ИИ | https://grok.com/ | все | nox-m-mobile.js: единая кнопка ИИ | P0 |
| Grok app | тёмная тема | https://grok.com/ | все | уже тёмное стекло | P2 |
| Meta AI | плавающая кнопка ИИ | https://www.meta.ai/ | все | nox-m-mobile.js: единая кнопка ИИ | P0 |
| Meta AI | нижняя шторка | https://www.meta.ai/ | все модалки | nox-m-mobile.js: sheet | P0 |
| Character.AI | нижний таб-бар | https://character.ai/ | все страницы | nox-m-mobile.js: таб-бар | P0 |
| Character.AI | свайп-жесты/назад | https://character.ai/ | все (назад) | nox-m-mobile.js: edge-swipe back | P0 |
| Character.AI | карусель историй | https://character.ai/ | index, news, glance | Swiper/embla карусель | P2 |
| DeepSeek app | тёмная тема | https://www.deepseek.com/ | все | уже тёмное стекло | P2 |
| DeepSeek app | нижняя шторка | https://www.deepseek.com/ | все модалки | nox-m-mobile.js: sheet | P0 |
| Mistral Le Chat | нижняя шторка | https://chat.mistral.ai/ | все модалки | nox-m-mobile.js: sheet | P0 |
| Mistral Le Chat | тёмная тема | https://chat.mistral.ai/ | все | уже тёмное стекло | P2 |
| Poe | нижний таб-бар | https://poe.com/ | все страницы | nox-m-mobile.js: таб-бар | P0 |
| Poe | нижняя шторка | https://poe.com/ | все модалки | nox-m-mobile.js: sheet | P0 |
| Notion | нижний таб-бар | https://www.notion.com/mobile | все страницы | nox-m-mobile.js: таб-бар | P0 |
| Notion | нижняя шторка | https://www.notion.com/mobile | все модалки | nox-m-mobile.js: sheet | P0 |
| Notion | поиск сверху | https://www.notion.com/mobile | index, chat, knowledge | поиск сверху (nox-cmd) | P1 |
| Notion | плавающая кнопка ИИ | https://www.notion.com/mobile | все | nox-m-mobile.js: единая кнопка ИИ | P0 |
| Obsidian mobile | нижняя шторка | https://obsidian.md/mobile | все модалки | nox-m-mobile.js: sheet | P0 |
| Obsidian mobile | свайп-жесты/назад | https://obsidian.md/mobile | все (назад) | nox-m-mobile.js: edge-swipe back | P0 |
| Obsidian mobile | поиск сверху | https://obsidian.md/mobile | index, chat, knowledge | поиск сверху (nox-cmd) | P1 |
| Todoist | плавающая кнопка ИИ | https://todoist.com/ | все | nox-m-mobile.js: единая кнопка ИИ | P0 |
| Todoist | нижняя шторка | https://todoist.com/ | все модалки | nox-m-mobile.js: sheet | P0 |
| Todoist | свайп-жесты/назад | https://todoist.com/ | все (назад) | nox-m-mobile.js: edge-swipe back | P0 |
| Things 3 | нижняя шторка | https://culturedcode.com/things/ | все модалки | nox-m-mobile.js: sheet | P0 |
| Things 3 | свайп-жесты/назад | https://culturedcode.com/things/ | все (назад) | nox-m-mobile.js: edge-swipe back | P0 |
| Things 3 | haptics | https://culturedcode.com/things/ | все | ios-haptics | P1 |
| Linear mobile | нижний таб-бар | https://linear.app/mobile | все страницы | nox-m-mobile.js: таб-бар | P0 |
| Linear mobile | нижняя шторка | https://linear.app/mobile | все модалки | nox-m-mobile.js: sheet | P0 |
| Linear mobile | свайп-жесты/назад | https://linear.app/mobile | все (назад) | nox-m-mobile.js: edge-swipe back | P0 |
| Spotify | нижний таб-бар | https://open.spotify.com/ | все страницы | nox-m-mobile.js: таб-бар | P0 |
| Spotify | нижняя шторка | https://open.spotify.com/ | все модалки | nox-m-mobile.js: sheet | P0 |
| Spotify | свайп-жесты/назад | https://open.spotify.com/ | все (назад) | nox-m-mobile.js: edge-swipe back | P0 |
| Spotify | карусель историй | https://open.spotify.com/ | index, news, glance | Swiper/embla карусель | P2 |
| Spotify | тёмная тема | https://open.spotify.com/ | все | уже тёмное стекло | P2 |
| Netflix | нижний таб-бар | https://www.netflix.com/ | все страницы | nox-m-mobile.js: таб-бар | P0 |
| Netflix | карусель историй | https://www.netflix.com/ | index, news, glance | Swiper/embla карусель | P2 |
| Netflix | тёмная тема | https://www.netflix.com/ | все | уже тёмное стекло | P2 |
| Netflix | поиск сверху | https://www.netflix.com/ | index, chat, knowledge | поиск сверху (nox-cmd) | P1 |
| Airbnb | нижний таб-бар | https://www.airbnb.com/ | все страницы | nox-m-mobile.js: таб-бар | P0 |
| Airbnb | поиск сверху | https://www.airbnb.com/ | index, chat, knowledge | поиск сверху (nox-cmd) | P1 |
| Airbnb | нижняя шторка | https://www.airbnb.com/ | все модалки | nox-m-mobile.js: sheet | P0 |
| Airbnb | карусель историй | https://www.airbnb.com/ | index, news, glance | Swiper/embla карусель | P2 |
| Uber | нижний таб-бар | https://www.uber.com/ | все страницы | nox-m-mobile.js: таб-бар | P0 |
| Uber | нижняя шторка | https://www.uber.com/ | все модалки | nox-m-mobile.js: sheet | P0 |
| Uber | сервисная сетка «всё в одном» | https://www.uber.com/ | Ещё (шторка) | nox-m-mobile.js: сетка сервисов | P0 |
| Uber | поиск сверху | https://www.uber.com/ | index, chat, knowledge | поиск сверху (nox-cmd) | P1 |
| Bolt | нижний таб-бар | https://bolt.eu/ | все страницы | nox-m-mobile.js: таб-бар | P0 |
| Bolt | нижняя шторка | https://bolt.eu/ | все модалки | nox-m-mobile.js: sheet | P0 |
| Instagram | нижний таб-бар | https://www.instagram.com/ | все страницы | nox-m-mobile.js: таб-бар | P0 |
| Instagram | карусель историй | https://www.instagram.com/ | index, news, glance | Swiper/embla карусель | P2 |
| Instagram | свайп-жесты/назад | https://www.instagram.com/ | все (назад) | nox-m-mobile.js: edge-swipe back | P0 |
| Instagram | pull-to-refresh | https://www.instagram.com/ | news, glance, dispatcher, downloads | nox-m-mobile.js: pull-to-refresh | P1 |
| TikTok | нижний таб-бар | https://www.tiktok.com/ | все страницы | nox-m-mobile.js: таб-бар | P0 |
| TikTok | свайп-жесты/назад | https://www.tiktok.com/ | все (назад) | nox-m-mobile.js: edge-swipe back | P0 |
| TikTok | нижняя шторка | https://www.tiktok.com/ | все модалки | nox-m-mobile.js: sheet | P0 |
| TikTok | тёмная тема | https://www.tiktok.com/ | все | уже тёмное стекло | P2 |
| X (Twitter) | нижний таб-бар | https://x.com/ | все страницы | nox-m-mobile.js: таб-бар | P0 |
| X (Twitter) | плавающая кнопка ИИ | https://x.com/ | все | nox-m-mobile.js: единая кнопка ИИ | P0 |
| X (Twitter) | pull-to-refresh | https://x.com/ | news, glance, dispatcher, downloads | nox-m-mobile.js: pull-to-refresh | P1 |
| X (Twitter) | свайп-жесты/назад | https://x.com/ | все (назад) | nox-m-mobile.js: edge-swipe back | P0 |
| Threads | нижний таб-бар | https://www.threads.net/ | все страницы | nox-m-mobile.js: таб-бар | P0 |
| Threads | pull-to-refresh | https://www.threads.net/ | news, glance, dispatcher, downloads | nox-m-mobile.js: pull-to-refresh | P1 |
| Threads | плавающая кнопка ИИ | https://www.threads.net/ | все | nox-m-mobile.js: единая кнопка ИИ | P0 |
| Snapchat | нижний таб-бар | https://www.snapchat.com/ | все страницы | nox-m-mobile.js: таб-бар | P0 |
| Snapchat | свайп-жесты/назад | https://www.snapchat.com/ | все (назад) | nox-m-mobile.js: edge-swipe back | P0 |
| Snapchat | карусель историй | https://www.snapchat.com/ | index, news, glance | Swiper/embla карусель | P2 |
| WhatsApp | нижний таб-бар | https://www.whatsapp.com/ | все страницы | nox-m-mobile.js: таб-бар | P0 |
| WhatsApp | свайп-жесты/назад | https://www.whatsapp.com/ | все (назад) | nox-m-mobile.js: edge-swipe back | P0 |
| WhatsApp | поиск сверху | https://www.whatsapp.com/ | index, chat, knowledge | поиск сверху (nox-cmd) | P1 |
| WhatsApp | плавающая кнопка ИИ | https://www.whatsapp.com/ | все | nox-m-mobile.js: единая кнопка ИИ | P0 |
| Signal | свайп-жесты/назад | https://signal.org/ | все (назад) | nox-m-mobile.js: edge-swipe back | P0 |
| Signal | поиск сверху | https://signal.org/ | index, chat, knowledge | поиск сверху (nox-cmd) | P1 |
| Signal | плавающая кнопка ИИ | https://signal.org/ | все | nox-m-mobile.js: единая кнопка ИИ | P0 |
| LINE | нижний таб-бар | https://line.me/ | все страницы | nox-m-mobile.js: таб-бар | P0 |
| LINE | сервисная сетка «всё в одном» | https://line.me/ | Ещё (шторка) | nox-m-mobile.js: сетка сервисов | P0 |
| LINE | карусель историй | https://line.me/ | index, news, glance | Swiper/embla карусель | P2 |
| KakaoTalk | нижний таб-бар | https://www.kakaocorp.com/page/service/service/KakaoTalk | все страницы | nox-m-mobile.js: таб-бар | P0 |
| KakaoTalk | сервисная сетка «всё в одном» | https://www.kakaocorp.com/page/service/service/KakaoTalk | Ещё (шторка) | nox-m-mobile.js: сетка сервисов | P0 |
| KakaoTalk | нижняя шторка | https://www.kakaocorp.com/page/service/service/KakaoTalk | все модалки | nox-m-mobile.js: sheet | P0 |
| Naver | поиск сверху | https://www.naver.com/ | index, chat, knowledge | поиск сверху (nox-cmd) | P1 |
| Naver | сервисная сетка «всё в одном» | https://www.naver.com/ | Ещё (шторка) | nox-m-mobile.js: сетка сервисов | P0 |
| Naver | нижний таб-бар | https://www.naver.com/ | все страницы | nox-m-mobile.js: таб-бар | P0 |
| Paytm | сервисная сетка «всё в одном» | https://paytm.com/ | Ещё (шторка) | nox-m-mobile.js: сетка сервисов | P0 |
| Paytm | нижний таб-бар | https://paytm.com/ | все страницы | nox-m-mobile.js: таб-бар | P0 |
| Paytm | поиск сверху | https://paytm.com/ | index, chat, knowledge | поиск сверху (nox-cmd) | P1 |
| PhonePe | сервисная сетка «всё в одном» | https://www.phonepe.com/ | Ещё (шторка) | nox-m-mobile.js: сетка сервисов | P0 |
| PhonePe | нижний таб-бар | https://www.phonepe.com/ | все страницы | nox-m-mobile.js: таб-бар | P0 |
| PhonePe | карусель историй | https://www.phonepe.com/ | index, news, glance | Swiper/embla карусель | P2 |
| Google Pay India | сервисная сетка «всё в одном» | https://pay.google.com/intl/en_in/about/ | Ещё (шторка) | nox-m-mobile.js: сетка сервисов | P0 |
| Google Pay India | нижний таб-бар | https://pay.google.com/intl/en_in/about/ | все страницы | nox-m-mobile.js: таб-бар | P0 |
| Google Pay India | нижняя шторка | https://pay.google.com/intl/en_in/about/ | все модалки | nox-m-mobile.js: sheet | P0 |
| GCash | сервисная сетка «всё в одном» | https://www.gcash.com/ | Ещё (шторка) | nox-m-mobile.js: сетка сервисов | P0 |
| GCash | нижний таб-бар | https://www.gcash.com/ | все страницы | nox-m-mobile.js: таб-бар | P0 |
| Rappi | сервисная сетка «всё в одном» | https://www.rappi.com/ | Ещё (шторка) | nox-m-mobile.js: сетка сервисов | P0 |
| Rappi | нижний таб-бар | https://www.rappi.com/ | все страницы | nox-m-mobile.js: таб-бар | P0 |
| Rappi | поиск сверху | https://www.rappi.com/ | index, chat, knowledge | поиск сверху (nox-cmd) | P1 |
| Mercado Libre / Mercado Pago | нижний таб-бар | https://www.mercadolibre.com/ | все страницы | nox-m-mobile.js: таб-бар | P0 |
| Mercado Libre / Mercado Pago | сервисная сетка «всё в одном» | https://www.mercadolibre.com/ | Ещё (шторка) | nox-m-mobile.js: сетка сервисов | P0 |
| Mercado Libre / Mercado Pago | поиск сверху | https://www.mercadolibre.com/ | index, chat, knowledge | поиск сверху (nox-cmd) | P1 |
| Meituan | сервисная сетка «всё в одном» | https://about.meituan.com/ | Ещё (шторка) | nox-m-mobile.js: сетка сервисов | P0 |
| Meituan | нижний таб-бар | https://about.meituan.com/ | все страницы | nox-m-mobile.js: таб-бар | P0 |
| Meituan | поиск сверху | https://about.meituan.com/ | index, chat, knowledge | поиск сверху (nox-cmd) | P1 |
| Douyin | нижний таб-бар | https://www.douyin.com/ | все страницы | nox-m-mobile.js: таб-бар | P0 |
| Douyin | свайп-жесты/назад | https://www.douyin.com/ | все (назад) | nox-m-mobile.js: edge-swipe back | P0 |
| Douyin | нижняя шторка | https://www.douyin.com/ | все модалки | nox-m-mobile.js: sheet | P0 |
| Xiaohongshu | нижний таб-бар | https://www.xiaohongshu.com/ | все страницы | nox-m-mobile.js: таб-бар | P0 |
| Xiaohongshu | свайп-жесты/назад | https://www.xiaohongshu.com/ | все (назад) | nox-m-mobile.js: edge-swipe back | P0 |
| Xiaohongshu | поиск сверху | https://www.xiaohongshu.com/ | index, chat, knowledge | поиск сверху (nox-cmd) | P1 |
| Bitrix/VK Work, Ozon | нижний таб-бар | https://www.ozon.ru/ | все страницы | nox-m-mobile.js: таб-бар | P0 |
| Bitrix/VK Work, Ozon | поиск сверху | https://www.ozon.ru/ | index, chat, knowledge | поиск сверху (nox-cmd) | P1 |
| Bitrix/VK Work, Ozon | сервисная сетка «всё в одном» | https://www.ozon.ru/ | Ещё (шторка) | nox-m-mobile.js: сетка сервисов | P0 |
| Wildberries | нижний таб-бар | https://www.wildberries.ru/ | все страницы | nox-m-mobile.js: таб-бар | P0 |
| Wildberries | поиск сверху | https://www.wildberries.ru/ | index, chat, knowledge | поиск сверху (nox-cmd) | P1 |
| Wildberries | сервисная сетка «всё в одном» | https://www.wildberries.ru/ | Ещё (шторка) | nox-m-mobile.js: сетка сервисов | P0 |
| Avito | нижний таб-бар | https://www.avito.ru/ | все страницы | nox-m-mobile.js: таб-бар | P0 |
| Avito | поиск сверху | https://www.avito.ru/ | index, chat, knowledge | поиск сверху (nox-cmd) | P1 |
| Avito | нижняя шторка | https://www.avito.ru/ | все модалки | nox-m-mobile.js: sheet | P0 |
| Госуслуги | сервисная сетка «всё в одном» | https://www.gosuslugi.ru/ | Ещё (шторка) | nox-m-mobile.js: сетка сервисов | P0 |
| Госуслуги | поиск сверху | https://www.gosuslugi.ru/ | index, chat, knowledge | поиск сверху (nox-cmd) | P1 |
| Госуслуги | нижний таб-бар | https://www.gosuslugi.ru/ | все страницы | nox-m-mobile.js: таб-бар | P0 |
| Duolingo | нижний таб-бар | https://www.duolingo.com/ | все страницы | nox-m-mobile.js: таб-бар | P0 |
| Duolingo | карусель историй | https://www.duolingo.com/ | index, news, glance | Swiper/embla карусель | P2 |
| Duolingo | haptics | https://www.duolingo.com/ | все | ios-haptics | P1 |
| Duolingo | крупные цели | https://www.duolingo.com/ | все | nox-m-mobile.css: 44px | P0 |
| Headspace/Calm | нижний таб-бар | https://www.headspace.com/ | все страницы | nox-m-mobile.js: таб-бар | P0 |
| Headspace/Calm | карусель историй | https://www.headspace.com/ | index, news, glance | Swiper/embla карусель | P2 |
| Headspace/Calm | тёмная тема | https://www.headspace.com/ | все | уже тёмное стекло | P2 |
| Strava | нижний таб-бар | https://www.strava.com/ | все страницы | nox-m-mobile.js: таб-бар | P0 |
| Strava | нижняя шторка | https://www.strava.com/ | все модалки | nox-m-mobile.js: sheet | P0 |
| Strava | карусель историй | https://www.strava.com/ | index, news, glance | Swiper/embla карусель | P2 |
| Cash App | нижний таб-бар | https://cash.app/ | все страницы | nox-m-mobile.js: таб-бар | P0 |
| Cash App | нижняя шторка | https://cash.app/ | все модалки | nox-m-mobile.js: sheet | P0 |
| Cash App | haptics | https://cash.app/ | все | ios-haptics | P1 |
| Wise | нижний таб-бар | https://wise.com/ | все страницы | nox-m-mobile.js: таб-бар | P0 |
| Wise | нижняя шторка | https://wise.com/ | все модалки | nox-m-mobile.js: sheet | P0 |
| N26 | нижний таб-бар | https://n26.com/ | все страницы | nox-m-mobile.js: таб-бар | P0 |
| N26 | карусель историй | https://n26.com/ | index, news, glance | Swiper/embla карусель | P2 |
| N26 | нижняя шторка | https://n26.com/ | все модалки | nox-m-mobile.js: sheet | P0 |
| Nubank | нижний таб-бар | https://nubank.com.br/ | все страницы | nox-m-mobile.js: таб-бар | P0 |
| Nubank | сервисная сетка «всё в одном» | https://nubank.com.br/ | Ещё (шторка) | nox-m-mobile.js: сетка сервисов | P0 |
| Nubank | карусель историй | https://nubank.com.br/ | index, news, glance | Swiper/embla карусель | P2 |
