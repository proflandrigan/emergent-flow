import { useEffect, useState } from "react";

export interface Persona {
  slug: string;
  label: string;
  description: string;
  node_families: string[];
  system_prompt?: string | null;
  source_path?: string | null;
}

export function usePersonas(): Persona[] {
  const [personas, setPersonas] = useState<Persona[]>([]);
  useEffect(() => {
    let cancelled = false;
    fetch("/personas")
      .then((res) => res.json() as Promise<{ personas: Persona[] }>)
      .then((data) => {
        if (!cancelled && data && Array.isArray(data.personas)) {
          setPersonas(data.personas);
        }
      })
      .catch(() => {
        /* keep the empty fallback */
      });
    return () => {
      cancelled = true;
    };
  }, []);
  return personas;
}
