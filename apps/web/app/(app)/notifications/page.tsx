import type { Metadata } from "next";
import { NotificationsList } from "./_components/NotificationsList";

export const metadata: Metadata = { title: "Notifications" };

export default function NotificationsPage() {
  return <NotificationsList />;
}
