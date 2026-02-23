import { useState, useEffect } from 'react';

export default function ErrorCard({ title = 'Panel', onRetry }) {
  const [countdown, setCountdown] = useState(30);

  useEffect(() => {
    const iv = setInterval(() => {
      setCountdown(c => {
        if (c <= 1) {
          onRetry?.();
          return 30;
        }
        return c - 1;
      });
    }, 1000);
    return () => clearInterval(iv);
  }, [onRetry]);

  return (
    <div className="bg-gray-900 rounded-xl p-6 border border-red-900/30">
      <div className="flex items-center gap-2 text-red-400 mb-2">
        <span>⚠️</span>
        <h3 className="text-sm font-bold">{title}</h3>
      </div>
      <p className="text-xs text-gray-500">Data unavailable — retrying in {countdown}s</p>
      <button onClick={onRetry} className="mt-2 text-xs text-emerald-400 hover:underline">Retry now</button>
    </div>
  );
}
