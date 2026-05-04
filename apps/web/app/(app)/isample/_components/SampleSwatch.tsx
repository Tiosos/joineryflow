interface Props {
  hexSwatch: string;
  photoFileBlobId: number | null;
}

export default function SampleSwatch({ hexSwatch, photoFileBlobId }: Props) {
  if (photoFileBlobId != null) {
    return (
      <div
        className="relative h-full w-full bg-cover bg-center"
        style={{ backgroundImage: `url(/api/files/${photoFileBlobId})` }}
        aria-label={`Sample photo (hex ${hexSwatch})`}
      >
        {/* Hex chip in bottom-right when photo is present */}
        <div
          className="absolute bottom-2 right-2 h-3 w-3 rounded-sm border-2 border-white shadow"
          style={{ background: hexSwatch }}
          title={`Hex ${hexSwatch}`}
        />
      </div>
    );
  }
  return (
    <div
      className="relative h-full w-full"
      style={{ background: hexSwatch }}
      aria-label={`Swatch ${hexSwatch}`}
    >
      {/* 135° sheen overlay */}
      <div
        className="absolute inset-0"
        style={{
          backgroundImage:
            "repeating-linear-gradient(135deg, rgba(255,255,255,0.04) 0 2px, transparent 2px 6px)",
        }}
      />
    </div>
  );
}
