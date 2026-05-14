import { NavLink } from "react-router-dom";
import { useState, useEffect } from "react";
import { Newspaper, Headphones, Radio, Video, TrendingUp, Bell, BellOff, Moon, Sun } from "lucide-react";
import LanguageToggle from "./LanguageToggle";
import { registerPush, unregisterPush, isPushSubscribed } from "../services/push";

const navItems = [
  { to: "/", label: "Digest", labelCn: "\u65E5\u62A5", icon: Newspaper },
  { to: "/podcasts", label: "Podcasts", labelCn: "\u64AD\u5BA2", icon: Headphones },
  { to: "/predictions", label: "Predictions", labelCn: "\u9884\u6D4B", icon: TrendingUp },
  { to: "/livestreams", label: "Live", labelCn: "\u76F4\u64AD", icon: Radio },
  { to: "/media", label: "Media", labelCn: "\u5A92\u4F53", icon: Video },
];

export default function Navbar() {
  const [pushEnabled, setPushEnabled] = useState(false);
  const [darkMode, setDarkMode] = useState(
    () => localStorage.getItem("theme") === "dark",
  );

  useEffect(() => {
    isPushSubscribed().then(setPushEnabled);
  }, []);

  useEffect(() => {
    document.documentElement.classList.toggle("dark", darkMode);
    localStorage.setItem("theme", darkMode ? "dark" : "light");
  }, [darkMode]);

  const togglePush = async () => {
    try {
      if (pushEnabled) {
        await unregisterPush();
        setPushEnabled(false);
      } else {
        await registerPush();
        setPushEnabled(true);
      }
    } catch (err) {
      console.error("Push toggle failed:", err);
    }
  };

  return (
    <header className="sticky top-0 z-50 border-b border-stone-200/80 dark:border-stone-800/80 bg-stone-50/90 dark:bg-stone-950/90 backdrop-blur-lg">
      <div className="mx-auto max-w-3xl flex items-center justify-between px-6 py-4">
        <div className="flex items-center gap-1">
          <h1 className="font-serif text-xl tracking-tight mr-8 text-stone-900 dark:text-stone-100">
            Daily AI News
          </h1>
          <nav className="flex gap-0.5">
            {navItems.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.to === "/"}
                className={({ isActive }) =>
                  `flex items-center gap-1.5 px-3 py-1.5 text-[13px] font-medium tracking-wide uppercase transition-all duration-200 border-b-2 ${
                    isActive
                      ? "border-accent text-accent dark:text-amber-500 dark:border-amber-500"
                      : "border-transparent text-stone-500 dark:text-stone-500 hover:text-stone-800 dark:hover:text-stone-300"
                  }`
                }
              >
                <item.icon size={14} strokeWidth={1.5} />
                {item.label}
              </NavLink>
            ))}
          </nav>
        </div>

        <div className="flex items-center gap-1">
          <LanguageToggle />
          <button
            onClick={togglePush}
            className="rounded-full p-2 text-stone-400 hover:text-stone-700 dark:hover:text-stone-200 hover:bg-stone-200/50 dark:hover:bg-stone-800/50 transition-all duration-200"
            title={pushEnabled ? "Disable notifications" : "Enable notifications"}
          >
            {pushEnabled ? <Bell size={16} strokeWidth={1.5} /> : <BellOff size={16} strokeWidth={1.5} />}
          </button>
          <button
            onClick={() => setDarkMode(!darkMode)}
            className="rounded-full p-2 text-stone-400 hover:text-stone-700 dark:hover:text-stone-200 hover:bg-stone-200/50 dark:hover:bg-stone-800/50 transition-all duration-200"
          >
            {darkMode ? <Sun size={16} strokeWidth={1.5} /> : <Moon size={16} strokeWidth={1.5} />}
          </button>
        </div>
      </div>
    </header>
  );
}
