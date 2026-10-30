import { useEffect, useState } from "react";

export interface PageActivity {
  visible: boolean;
  online: boolean;
}

function readActivity(): PageActivity {
  return {
    visible:
      typeof document === "undefined" || document.visibilityState === "visible",
    online: typeof navigator === "undefined" || navigator.onLine,
  };
}

export function usePageActivity(): PageActivity {
  const [activity, setActivity] = useState<PageActivity>(readActivity);

  useEffect(() => {
    const update = () => setActivity(readActivity());
    document.addEventListener("visibilitychange", update);
    window.addEventListener("online", update);
    window.addEventListener("offline", update);
    return () => {
      document.removeEventListener("visibilitychange", update);
      window.removeEventListener("online", update);
      window.removeEventListener("offline", update);
    };
  }, []);

  return activity;
}
