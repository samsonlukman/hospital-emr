import { useState } from "react";
import { AppIcon } from "./icons";

export const SESSION_PHOTO_HREF = "/openmrs/abikan-api/session/photo";

export function AccountPhoto({
  className,
  fallbackClassName,
  alt = "",
  showIconFallback = false,
}: {
  className: string;
  fallbackClassName?: string;
  alt?: string;
  showIconFallback?: boolean;
}) {
  const [ready, setReady] = useState(false);

  return (
    <>
      {ready ? null : (
        <span className={fallbackClassName ?? className} aria-hidden="true">
          {showIconFallback ? <AppIcon name="user" size={18} /> : null}
        </span>
      )}
      <img
        className={className}
        src={SESSION_PHOTO_HREF}
        alt={alt}
        hidden={!ready}
        onLoad={() => setReady(true)}
        onError={() => setReady(false)}
      />
    </>
  );
}
