import { PageHeader } from "@/presentation/components/ui";

export default function Layout({ children }: { children: React.ReactNode }) {
  return (
    <>
      <PageHeader title="Check voice" crumbs={[{ label: "Customers", href: "/customers" }, { label: "Check voice" }]} subtitle="Check that the person speaking is really the customer." />
      {children}
    </>
  );
}
