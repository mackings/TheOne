import { PageHeader } from "@/presentation/components/ui";

export default function Layout({ children }: { children: React.ReactNode }) {
  return (
    <>
      <PageHeader title="Set up voice" crumbs={[{ label: "Customers", href: "/customers" }, { label: "Set up voice" }]} subtitle="The customer reads a few short phrases so TheOne can recognise their voice later." />
      {children}
    </>
  );
}
