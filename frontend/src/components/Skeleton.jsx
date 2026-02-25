export function SkeletonCard({ height = 'h-40' }) {
  return (
    <div className={`u-card p-6 ${height} animate-pulse`}>
      <div className="h-4 bg-zinc-800 rounded w-1/3 mb-4"></div>
      <div className="h-3 bg-zinc-800 rounded w-2/3 mb-3"></div>
      <div className="h-3 bg-zinc-800 rounded w-1/2 mb-3"></div>
      <div className="h-3 bg-zinc-800 rounded w-3/4"></div>
    </div>
  );
}

export function SkeletonGrid({ count = 4 }) {
  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
      {Array.from({ length: count }, (_, i) => (
        <SkeletonCard key={i} height="h-32" />
      ))}
    </div>
  );
}
