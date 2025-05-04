import "./globals.css";
import { ThemeProvider } from "next-themes";
import { Exo_2, Schibsted_Grotesk, Geist } from 'next/font/google';
import { Toaster } from 'sonner';
import 'katex/dist/katex.min.css';

const exo_2 = Exo_2({
  subsets: ['latin'],
  weight: ['800'],
  variable: '--display-family',
});

const schibsted_grotesk = Schibsted_Grotesk({
  subsets: ['latin'],
  weight: ['700'],
  variable: '--text-family',
});

const geist = Geist({
  subsets: ['latin'],
  weight: ['700'],
  variable: '--geist-family',
});

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className={`${exo_2.variable} ${schibsted_grotesk.variable} ${geist.variable}`}>
        <ThemeProvider attribute="class" defaultTheme="system" enableSystem>
          {children}
        </ThemeProvider>
      </body>
    </html>
  );
}
