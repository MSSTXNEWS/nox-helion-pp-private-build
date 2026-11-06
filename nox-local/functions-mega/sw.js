/* NOX Local Service Worker: no fake server-side delivery claims. */
self.addEventListener('install',e=>self.skipWaiting());
self.addEventListener('activate',e=>e.waitUntil(self.clients.claim()));
self.addEventListener('push',e=>{
  let data={};try{data=e.data?.json()||{}}catch(err){data={body:e.data?.text()||''}}
  const title=typeof data.title==='string'?data.title:'NOX HELION';
  const body=typeof data.body==='string'?data.body:'Событие NOX';
  e.waitUntil(self.registration.showNotification(title,{body,tag:'nox-local-event',data:{url:'/chat.html'}}));
});
self.addEventListener('notificationclick',e=>{e.notification.close();e.waitUntil(self.clients.openWindow(e.notification.data?.url||'/chat.html'));});