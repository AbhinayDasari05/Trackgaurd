import React from 'react';
import { LocomotionMode } from '../types';
import { CircleDot, Cpu } from 'lucide-react';

interface Props {
  onSelectMode: (mode: LocomotionMode) => void;
}

export const Screen1ModeSelection: React.FC<Props> = ({ onSelectMode }) => {
  return (
    <div className="min-h-screen bg-[#070b14] flex flex-col justify-center items-center px-4 py-8 select-none">
      <div className="max-w-2xl w-full text-center space-y-8">
        
        {/* Project Name & Heading */}
        <div className="space-y-3">
          <h1 className="text-4xl sm:text-5xl font-black tracking-tight text-white font-mono">
            TRACK GUARD
          </h1>
          <p className="text-slate-300 text-lg sm:text-xl font-light tracking-wide">
            Select Locomotion Mode
          </p>
        </div>

        {/* Large Mode Selection Cards */}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-6 pt-4">
          
          {/* Wheel Mode */}
          <button
            onClick={() => onSelectMode('wheel')}
            className="group relative flex flex-col items-center text-center p-8 rounded-2xl bg-[#0d1527] border border-[#1f2d4d] hover:border-cyan-500 hover:shadow-[0_0_30px_rgba(6,182,212,0.25)] transition-all duration-300 transform hover:-translate-y-1 focus:outline-none focus:ring-2 focus:ring-cyan-400 cursor-pointer"
          >
            <div className="w-20 h-20 mb-6 rounded-2xl bg-cyan-950/50 border border-cyan-700/40 flex items-center justify-center text-cyan-400 group-hover:bg-cyan-500 group-hover:text-black transition-colors duration-300">
              <CircleDot className="w-10 h-10 transition-transform group-hover:scale-110 duration-300" />
            </div>
            
            <h2 className="text-2xl font-bold text-white group-hover:text-cyan-400 transition-colors">
              Wheel Mode
            </h2>
            
            <p className="mt-3 text-sm text-slate-400 leading-relaxed font-normal">
              High-efficiency motorized rolling locomotion for flat, paved corridors and smooth structured pathways.
            </p>

            <div className="mt-6 inline-flex items-center gap-1.5 text-xs font-mono text-cyan-500 font-semibold tracking-wider uppercase opacity-0 group-hover:opacity-100 transition-opacity">
              Activate Mode &rarr;
            </div>
          </button>

          {/* Integrated Mode */}
          <button
            onClick={() => onSelectMode('integrated')}
            className="group relative flex flex-col items-center text-center p-8 rounded-2xl bg-[#0d1527] border border-[#1f2d4d] hover:border-blue-500 hover:shadow-[0_0_30px_rgba(59,130,246,0.25)] transition-all duration-300 transform hover:-translate-y-1 focus:outline-none focus:ring-2 focus:ring-blue-400 cursor-pointer"
          >
            <div className="w-20 h-20 mb-6 rounded-2xl bg-blue-950/50 border border-blue-700/40 flex items-center justify-center text-blue-400 group-hover:bg-blue-500 group-hover:text-black transition-colors duration-300">
              <Cpu className="w-10 h-10 transition-transform group-hover:scale-110 duration-300" />
            </div>

            <h2 className="text-2xl font-bold text-white group-hover:text-blue-400 transition-colors">
              Integrated Mode
            </h2>

            <p className="mt-3 text-sm text-slate-400 leading-relaxed font-normal">
              Hybrid articulated wheeled-leg locomotion for irregular terrain, elevated obstacles, and off-road paths.
            </p>

            <div className="mt-6 inline-flex items-center gap-1.5 text-xs font-mono text-blue-500 font-semibold tracking-wider uppercase opacity-0 group-hover:opacity-100 transition-opacity">
              Activate Mode &rarr;
            </div>
          </button>

        </div>

      </div>
    </div>
  );
};
