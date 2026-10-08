import GenerationStudio from "@/components/organic/generation-studio";
import { OrganicHeader } from "@/components/organic/shared";

// Photo Generation (SPEC-FE-050 / SPEC-BE-077).
export default function PhotoPage() {
  return (
    <>
      <OrganicHeader title="Photo Generation" subtitle="Prompt → preview → regenerate or edit → approve → use in a post." />
      <GenerationStudio kind="image" />
    </>
  );
}
