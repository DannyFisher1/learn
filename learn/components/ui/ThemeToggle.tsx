'use client';

import { useTheme } from 'next-themes';
import { useEffect, useState } from 'react';
// --- Use Radix Icons --- 
// import { Sun, Moon } from 'lucide-react';
import { SunIcon, MoonIcon } from '@radix-ui/react-icons';
// -----------------------
import { Button } from './button';

export default function ThemeToggle() {
  const { theme, setTheme } = useTheme();
  const [mounted, setMounted] = useState(false);

  useEffect(() => setMounted(true), []);

  if (!mounted) return null;

  return (
    <Button
      variant="ghost"
      size="icon"
      aria-label="Toggle theme"
      onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}
    >
      {/* --- Use Radix Icons --- */}
      {theme === 'dark' ? <SunIcon className="h-5 w-5" /> : <MoonIcon className="h-5 w-5" />}
      {/* ----------------------- */}
    </Button>
  );
} 