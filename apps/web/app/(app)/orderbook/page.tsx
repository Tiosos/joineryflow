import { QueueClient } from "./_components/QueueClient";

export default async function Page({
  searchParams,
}: {
  searchParams: Promise<{ status?: string; supplier?: string; project_id?: string }>;
}) {
  const sp = await searchParams;
  return (
    <div className="grid gap-4">
      <header><h1 className="text-2xl font-semibold text-h-ink">Orderbook</h1></header>
      <QueueClient initial={sp} />
    </div>
  );
}
