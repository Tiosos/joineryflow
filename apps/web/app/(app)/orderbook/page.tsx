import { OrderbookTabs } from "./_components/OrderbookTabs";

/**
 * Orderbook. Two tabs since #10:
 *
 * - **Orders** (default) — `purchase_orders`, the commercial layer (Q505), and
 *   the surface Tracking's `?order=<po_number>` link lands on (Q418).
 * - **Queue** — #4's supplier-grouped procurement-batch queue, kept because
 *   Q504 leaves batches beneath orders as the allocation mechanism rather than
 *   replacing them.
 */
export default async function Page({
  searchParams,
}: {
  searchParams: Promise<{
    tab?: string;
    status?: string;
    supplier?: string;
    project_id?: string;
    order?: string;
  }>;
}) {
  const sp = await searchParams;
  return (
    <div className="grid gap-4">
      <header><h1 className="text-2xl font-semibold text-h-ink">Orderbook</h1></header>
      <OrderbookTabs initial={sp} />
    </div>
  );
}
