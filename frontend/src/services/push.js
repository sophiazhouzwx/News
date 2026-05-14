import { getVapidKey, subscribePush, unsubscribePush } from "./api";

function urlBase64ToUint8Array(base64String) {
  const padding = "=".repeat((4 - (base64String.length % 4)) % 4);
  const base64 = (base64String + padding).replace(/-/g, "+").replace(/_/g, "/");
  const rawData = window.atob(base64);
  return Uint8Array.from([...rawData].map((c) => c.charCodeAt(0)));
}

export async function registerPush() {
  if (!("serviceWorker" in navigator) || !("PushManager" in window)) {
    throw new Error("Push notifications not supported");
  }

  const registration = await navigator.serviceWorker.register("/sw.js");
  const vapidKey = await getVapidKey();

  const subscription = await registration.pushManager.subscribe({
    userVisibleOnly: true,
    applicationServerKey: urlBase64ToUint8Array(vapidKey),
  });

  const sub = subscription.toJSON();
  await subscribePush(sub.endpoint, sub.keys);
  return subscription;
}

export async function unregisterPush() {
  const registration = await navigator.serviceWorker.ready;
  const subscription = await registration.pushManager.getSubscription();
  if (subscription) {
    const sub = subscription.toJSON();
    await unsubscribePush(sub.endpoint, sub.keys);
    await subscription.unsubscribe();
  }
}

export async function isPushSubscribed() {
  if (!("serviceWorker" in navigator)) return false;
  try {
    const registration = await navigator.serviceWorker.ready;
    const subscription = await registration.pushManager.getSubscription();
    return !!subscription;
  } catch {
    return false;
  }
}
