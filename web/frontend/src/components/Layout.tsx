import { Outlet, useLocation } from "react-router-dom";
import { Sidebar } from "./Sidebar";
import { ToastContainer } from "./ui/Toast";
import { motion, AnimatePresence } from "framer-motion";

export function Layout() {
  const location = useLocation();

  return (
    <div className="flex min-h-screen bg-terminal-bg quant-subtle-grid">
      <Sidebar />
      <main className="relative flex-1 overflow-auto">
        {/* Top accent line */}
        <div className="absolute left-0 right-0 top-0 h-px bg-gradient-to-r from-terminal-green/50 via-terminal-cyan/25 to-transparent" />
        <div className="px-6 py-5">
          <AnimatePresence mode="wait">
            <motion.div
              key={location.pathname}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -4 }}
              transition={{ duration: 0.15, ease: "easeOut" }}
              className="mx-auto max-w-[1680px]"
            >
              <Outlet />
            </motion.div>
          </AnimatePresence>
        </div>
      </main>
      <ToastContainer />
    </div>
  );
}
