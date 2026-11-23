import { useRouter } from "next/router";
import { useEffect } from "react";

import { homeFor, useAuth } from "@/context/AuthContext";

export default function Home() {
  const { user, loading } = useAuth();
  const router = useRouter();
  useEffect(() => {
    if (!loading) void router.replace(user ? homeFor(user) : "/login");
  }, [user, loading, router]);
  return <div className="loading full">Loading…</div>;
}
