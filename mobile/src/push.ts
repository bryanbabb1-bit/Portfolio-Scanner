import Constants from "expo-constants";
import * as Device from "expo-device";
import * as Notifications from "expo-notifications";
import { Platform } from "react-native";
import { BACKEND_URL } from "./config";

// Register this device for push and hand the Expo token to the backend, which
// fans slaps out via the Expo push API. Returns the token or null.
export async function registerForPush(): Promise<string | null> {
  if (!Device.isDevice) return null; // simulators can't receive push

  const existing = await Notifications.getPermissionsAsync();
  let status = existing.status;
  if (status !== "granted") {
    const req = await Notifications.requestPermissionsAsync();
    status = req.status;
  }
  if (status !== "granted") return null;

  if (Platform.OS === "android") {
    await Notifications.setNotificationChannelAsync("watchdog", {
      name: "Watchdog signals",
      importance: Notifications.AndroidImportance.MAX,
      vibrationPattern: [0, 250, 250, 250],
      lightColor: "#38bdf8",
    });
  }

  const projectId =
    Constants.expoConfig?.extra?.eas?.projectId ??
    Constants.easConfig?.projectId;
  let token: string;
  try {
    const res = await Notifications.getExpoPushTokenAsync(
      projectId ? { projectId } : undefined
    );
    token = res.data;
  } catch {
    return null;
  }

  try {
    await fetch(`${BACKEND_URL}/api/devices`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ token, platform: Platform.OS }),
    });
  } catch {
    // backend unreachable (tunnel down) — the app still works, just no push
  }
  return token;
}
