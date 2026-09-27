"use client";

import { useEffect, useRef } from "react";
import QRCode from "qrcode";

interface Props {
  itemId: number;
  itemNumber: number | null;
  code: string | null;
  description: string | null;
}

export function ItemLabelClient({ itemId, itemNumber, code, description }: Props) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  useEffect(() => {
    if (!canvasRef.current || itemNumber === null) return;
    QRCode.toCanvas(canvasRef.current, String(itemNumber), {
      width: 320,
      margin: 1,
    }).catch(() => {});
  }, [itemNumber]);

  return (
    <div className="flex min-h-screen flex-col items-center gap-6 bg-white p-8 text-black print:p-0">
      <div className="flex w-full max-w-sm flex-col items-center gap-4 rounded-lg border border-gray-300 p-6 print:border-none">
        {itemNumber === null ? (
          <p className="text-sm text-gray-500">
            This item has no joinery number yet.
          </p>
        ) : (
          <>
            <canvas ref={canvasRef} />
            <div className="text-center">
              <div className="font-mono text-2xl font-semibold tabular-nums">
                #{itemNumber}
              </div>
              {code && <div className="font-mono text-sm text-gray-600">{code}</div>}
              {description && (
                <div className="mt-1 max-w-xs text-sm text-gray-700">{description}</div>
              )}
            </div>
          </>
        )}
      </div>

      <button
        type="button"
        onClick={() => window.print()}
        className="rounded border border-gray-400 bg-gray-100 px-4 py-2 text-sm text-black hover:bg-gray-200 print:hidden"
      >
        Print label
      </button>
      <p className="max-w-sm text-center text-xs text-gray-500 print:hidden">
        Item #{itemId}. Scan this label to confirm the item when marking
        Packing done on Shop Floor.
      </p>
    </div>
  );
}
