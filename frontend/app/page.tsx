import { redirect } from "next/navigation";

// "/" has no content of its own: it redirects to the Dashboard (SPEC-FE-002).
export default function Page() {
  redirect("/dashboard");
}
