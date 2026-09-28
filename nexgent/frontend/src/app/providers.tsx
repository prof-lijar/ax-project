import { LANGUAGE_STORAGE_KEY, useLanguage } from "../shared/i18n";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { PropsWithChildren } from "react";
import { useEffect, useState } from "react";

export function AppProviders({ children }: PropsWithChildren) {
  const language = useLanguage((state) => state.language);
  useEffect(() => { document.documentElement.lang = language; }, [language]);
  useEffect(() => {
    const sync = (event: StorageEvent) => {
      if (event.storageArea === window.localStorage &&
          (event.key === LANGUAGE_STORAGE_KEY || event.key === null)) {
        useLanguage.setState({ language: event.newValue === "en" ? "en" : "ko" });
      }
    };
    window.addEventListener("storage", sync);
    return () => window.removeEventListener("storage", sync);
  }, []);
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            staleTime: 20_000,
            retry: 1,
            refetchOnWindowFocus: false
          }
        }
      })
  );

  return (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
}
