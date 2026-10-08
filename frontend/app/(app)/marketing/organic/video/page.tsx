import GenerationStudio from "@/components/organic/generation-studio";
import { OrganicHeader } from "@/components/organic/shared";

// Video Generation (SPEC-FE-050 / SPEC-BE-077). Providers make short clips;
// the page shows the length actually generated.
export default function VideoPage() {
  return (
    <>
      <OrganicHeader title="Video Generation" subtitle="Prompt → generation (a minute or more) → preview → regenerate → approve → use in a post." />
      <GenerationStudio kind="video" />
    </>
  );
}
