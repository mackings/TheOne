import { PageHeader } from "@/presentation/components/ui";

export default function Layout({ children }: { children: React.ReactNode }) {
  return (
    <>
      <PageHeader title="Iris (eye scan)" crumbs={[{ label: "Customers", href: "/customers" }, { label: "Iris" }]} subtitle="Set up a customer's eye scan, check it, or set a secret “I am in danger” eye." />
      {children}
    </>
  );
}
