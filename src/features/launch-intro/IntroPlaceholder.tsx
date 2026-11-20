import { useId, type ReactNode } from 'react';
import './intro-placeholder.css';

function Cockpit({ id }: { id: string }) {
  return (
    <svg className="intro-scene__cockpit" viewBox="0 0 1440 900" preserveAspectRatio="xMidYMid slice">
      <defs>
        <linearGradient id={`${id}-garage`} x2="0" y2="1">
          <stop stopColor="#101114" />
          <stop offset=".48" stopColor="#373635" />
          <stop offset="1" stopColor="#68615a" />
        </linearGradient>
        <linearGradient id={`${id}-floor`} x2="0" y2="1">
          <stop stopColor="#625d55" />
          <stop offset="1" stopColor="#202124" />
        </linearGradient>
        <linearGradient id={`${id}-paint`} x2=".36" y2="1">
          <stop stopColor="#fa3b4e" />
          <stop offset=".21" stopColor="#c90f2b" />
          <stop offset=".62" stopColor="#610818" />
          <stop offset="1" stopColor="#140a0e" />
        </linearGradient>
        <linearGradient id={`${id}-halo`} x2="0" y2="1">
          <stop stopColor="#545657" />
          <stop offset=".13" stopColor="#282a2c" />
          <stop offset=".8" stopColor="#131415" />
          <stop offset="1" stopColor="#050506" />
        </linearGradient>
        <pattern id={`${id}-weave`} width="8" height="8" patternUnits="userSpaceOnUse" patternTransform="rotate(-32)">
          <rect width="8" height="8" fill="#202123" />
          <path d="M0 0h4v4H0m4 0h4v4H4" fill="#292a2d" />
          <path d="M0 0h8M0 4h8" stroke="#101113" />
        </pattern>
      </defs>
      <g className="intro-scene__garage">
        <rect width="1440" height="900" fill={`url(#${id}-garage)`} />
        <path d="M0 362 510 185h420l510 177V0H0Z" fill="#161719" />
        <path d="M0 430 535 352h370l535 78v470H0Z" fill={`url(#${id}-floor)`} />
        <path d="M0 73 479 252V428L0 610Zm1440 0L961 252v176l479 182Z" fill="#242326" />
        <path d="M0 325 479 352M961 352l479-27" stroke="#b10e27" strokeWidth="6" />
        <path d="M487 230h466v187H487Z" fill="#767170" />
        <path d="M504 250h432v149H504Z" fill="#28282c" />
        <path d="M517 306h405m-405 42h405m-405 42h405" stroke="#474548" strokeWidth="2" />
        <path d="M520 254h400" stroke="#f4e9d8" strokeWidth="3" opacity=".75" />
        <path d="M253 0 541 218M1187 0 899 218M582 0l74 205M858 0l-74 205" stroke="#a0b9c5" strokeWidth="20" opacity=".1" />
        <path d="M253 0 541 218M1187 0 899 218M582 0l74 205M858 0l-74 205" stroke="#e4edeb" strokeWidth="5" />
        <path d="M607 421 320 890m513-469 287 469" stroke="#b9aea0" strokeWidth="3" opacity=".4" />
        <path d="M562 422 85 900m793-478 477 478" stroke="#9d2938" strokeWidth="8" opacity=".68" />
      </g>
      <g className="intro-scene__monocoque">
        <path d="M-100 365C231 260 492 167 720 196c228-29 489 64 820 169" fill="none" stroke="#070708" strokeWidth="79" />
        <path d="M-100 357C231 252 492 159 720 188c228-29 489 64 820 169" fill="none" stroke={`url(#${id}-halo)`} strokeWidth="55" />
        <path d="M-100 334C231 229 492 136 720 165c228-29 489 64 820 169" fill="none" stroke="#b7b8b9" strokeWidth="2" opacity=".45" />
        <path d="M697 181q23-10 46 0l-6 350h-34Z" fill={`url(#${id}-halo)`} stroke="#111214" strokeWidth="4" />
        <path d="M704 191q14-7 30-3" fill="none" stroke="#85868a" strokeWidth="2" />
        <path d="M0 509c233 38 378 143 485 222h470c107-79 252-184 485-222v391H0Z" fill={`url(#${id}-paint)`} />
        <path d="M0 517c254 54 416 197 521 264h398c105-67 267-210 521-264" fill="none" stroke="#f35765" strokeWidth="3" opacity=".58" />
        <path d="M0 584c252 65 369 216 500 230l62-244q158-52 316 0l62 244c131-14 248-165 500-230v316H0Z" fill={`url(#${id}-weave)`} stroke="#0b0b0d" strokeWidth="10" />
        <path d="M534 898 607 623q113-45 226 0l73 275" fill="#101013" stroke="#444448" strokeWidth="3" />
        <circle cx="720" cy="621" r="34" fill="#09090c" stroke="#6c6b6a" strokeWidth="4" />
        <circle cx="720" cy="621" r="19" fill="#26262b" stroke="#131316" strokeWidth="4" />
      </g>
    </svg>
  );
}

function SteeringWheel({ id }: { id: string }) {
  return (
    <svg className="intro-scene__wheel" viewBox="0 0 560 310">
      <defs>
        <linearGradient id={`${id}-rubber`} x2="0" y2="1">
          <stop stopColor="#5b5b61" />
          <stop offset=".35" stopColor="#2b2b32" />
          <stop offset="1" stopColor="#101014" />
        </linearGradient>
        <linearGradient id={`${id}-glove`} x2="0" y2="1">
          <stop stopColor="#dc263c" />
          <stop offset=".7" stopColor="#660e20" />
          <stop offset="1" stopColor="#260912" />
        </linearGradient>
      </defs>
      <path d="M0 310v-73l92-122 42 46L86 310Zm560 0v-73l-92-122-42 46 48 149Z" fill="#202024" />
      <path d="M55 261 72 145q7-36 35-46l58 42-38 88-42 48Zm450 0-17-116q-7-36-35-46l-58 42 38 88 42 48Z" fill={`url(#${id}-glove)`} stroke="#441018" strokeWidth="3" />
      <path d="M117 68q36-29 86-27h154q50-2 86 27l21 116q-15 43-52 48l-59-24H207l-59 24q-37-5-52-48Z" fill={`url(#${id}-weave)`} stroke="#09090a" strokeWidth="9" />
      <path d="M111 80q-21 53-13 101 3 16 17 25m334-126q21 53 13 101-3 16-17 25" fill="none" stroke={`url(#${id}-rubber)`} strokeWidth="35" strokeLinecap="round" />
      <rect x="194" y="73" width="172" height="77" rx="9" fill="#08090a" stroke="#55565b" strokeWidth="2" />
      <g className="intro-scene__shift-lights" stroke="#1a1618" strokeWidth="1.5">
        {[207, 228, 249, 270, 291, 312, 333, 354].map((x) => <circle key={x} cx={x} cy="60" r="5.8" />)}
      </g>
      <g className="intro-scene__wheel-display">
        <rect x="199" y="78" width="162" height="67" rx="6" fill="#2b3022" />
        <text x="280" y="105" textAnchor="middle" fill="#e5edca" fontSize="17" letterSpacing="1.5">JARROD</text>
        <text x="280" y="126" textAnchor="middle" fill="#b6d38b" fontSize="12" letterSpacing="2">P1 · READY</text>
      </g>
      <path d="M164 97v30m-15-15h30m217-15v30m-15-15h30" stroke="#09090a" strokeWidth="25" strokeLinecap="round" />
      <circle cx="164" cy="112" r="10" fill="#cc253f" stroke="#f77a82" strokeWidth="2" />
      <circle cx="396" cy="112" r="10" fill="#b2b488" stroke="#d7d5bf" strokeWidth="2" />
      <circle cx="206" cy="178" r="15" fill="#3b3d42" stroke="#929196" strokeWidth="2" />
      <circle cx="280" cy="178" r="17" fill="#3b3d42" stroke="#929196" strokeWidth="2" />
      <circle cx="354" cy="178" r="15" fill="#3b3d42" stroke="#929196" strokeWidth="2" />
      <path d="M206 174v-9m74 8v-11m74 12v-9" stroke="#e1dcd3" strokeWidth="2" />
      <path d="M63 201q11-45 24-60m410 60q-11-45-24-60" fill="none" stroke="#f7818c" strokeWidth="2" opacity=".45" />
    </svg>
  );
}

export function IntroPlaceholder({ children }: { children: ReactNode }) {
  const id = useId();

  return (
    <div className="intro-scene" aria-hidden="true" inert>
      <Cockpit id={id} />
      <SteeringWheel id={id} />
      <div className="intro-scene__vignette" />
      <div className="intro-scene__tablet">
        <div className="intro-scene__screen">
          <div className="intro-scene__telemetry">
            <span>JARROD LOW / PIT PANEL</span>
            <strong>LINK ESTABLISHED</strong>
            <div className="intro-scene__signal" />
          </div>
          <div className="intro-scene__page">{children}</div>
        </div>
      </div>
      <div className="intro-scene__visor" />
    </div>
  );
}
