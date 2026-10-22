import LandingPage from "@/components/landing/landing-page";

// "/" is the public PilotSonic website (pilotsonic-website.html). It sits
// outside the (app) group, so it has no shell and no sign-in guard; its
// buttons lead to /login, /signup or, when signed in, /dashboard.
export default function Page() {
  return <LandingPage />;
}
