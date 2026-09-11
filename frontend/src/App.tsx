import { useState, useEffect, useRef, useCallback } from 'react'
import './App.css'

// Strategy types matching the DLMM compiler
type StrategyType = 'spot' | 'curve' | 'bidask'

interface Strategy {
  type: StrategyType
  center: number
  width: number
  weight: number
  color: string
}

interface QAItem {
  question: string
  answer: string
  isOpen: boolean
}

// Generate Gaussian distribution
function gaussian(x: number, center: number, sigma: number): number {
  return Math.exp(-0.5 * Math.pow((x - center) / sigma, 2))
}

// Generate strategy shape - matching DLMM compiler shapes
// These are FIXED shapes - optimization only changes position, width, weight
function strategyShape(x: number, strategy: Strategy): number {
  const halfWidth = strategy.width / 2
  const left = strategy.center - halfWidth
  const right = strategy.center + halfWidth

  if (x < left || x > right) return 0

  // Normalized position within the shape (0 to 1)
  const pos = (x - left) / strategy.width

  switch (strategy.type) {
    case 'spot':
      // Spot = FLAT RECTANGLE (uniform height across entire width)
      return strategy.weight
    case 'curve':
      // Curve = DOME shape (parabola: 1 - 4*(pos-0.5)^2)
      const curveT = pos - 0.5
      return strategy.weight * Math.max(0, 1 - 4 * curveT * curveT)
    case 'bidask':
      // BidAsk = V-SHAPE (high at edges: 0 and 1, low at center: 0.5)
      return strategy.weight * Math.abs(pos - 0.5) * 2
    default:
      return 0
  }
}

// Optimize strategies to fit target (simplified greedy with diversity bonus)
function optimizeStrategies(
  target: number[],
  numStrategies: number,
  centerBin: number
): Strategy[] {
  const colors = ['#5B8A72', '#8B6B5B', '#6B5B8A', '#5B7A8A', '#8A5B6B']
  const strategies: Strategy[] = []
  const residual = [...target]
  const usedTypes: Set<StrategyType> = new Set()

  const types: StrategyType[] = ['curve', 'spot', 'bidask']

  for (let i = 0; i < numStrategies; i++) {
    let bestStrategy: Strategy | null = null
    let bestScore = -Infinity

    // Try different configurations
    for (const type of types) {
      for (let width = 15; width <= 55; width += 8) {
        for (let centerOffset = -15; centerOffset <= 15; centerOffset += 5) {
          const center = centerBin + centerOffset

          // Calculate optimal weight
          let numerator = 0
          let denominator = 0

          for (let x = 0; x < residual.length; x++) {
            const shape = strategyShape(x, { type, center, width, weight: 1, color: '' })
            numerator += residual[x] * shape
            denominator += shape * shape
          }

          if (denominator === 0) continue
          const weight = Math.max(0, numerator / denominator)

          // Calculate score (reduction in residual)
          let score = 0
          for (let x = 0; x < residual.length; x++) {
            const shape = strategyShape(x, { type, center, width, weight, color: '' })
            const oldResidual = residual[x] * residual[x]
            const newResidual = (residual[x] - shape) * (residual[x] - shape)
            score += oldResidual - newResidual
          }

          // Bonus for using a new strategy type (encourages diversity)
          if (!usedTypes.has(type)) {
            score *= 1.15
          }

          if (score > bestScore) {
            bestScore = score
            bestStrategy = { type, center, width, weight, color: colors[i % colors.length] }
          }
        }
      }
    }

    if (bestStrategy && bestStrategy.weight > 0.01) {
      strategies.push(bestStrategy)
      usedTypes.add(bestStrategy.type)
      // Update residual
      for (let x = 0; x < residual.length; x++) {
        residual[x] -= strategyShape(x, bestStrategy)
      }
    }
  }

  return strategies
}

// Calculate R² score
function calculateR2(target: number[], predicted: number[]): number {
  const mean = target.reduce((a, b) => a + b, 0) / target.length
  let ssRes = 0
  let ssTot = 0

  for (let i = 0; i < target.length; i++) {
    ssRes += Math.pow(target[i] - predicted[i], 2)
    ssTot += Math.pow(target[i] - mean, 2)
  }

  return ssTot === 0 ? 1 : 1 - (ssRes / ssTot)
}

function App() {
  const [showScrollIndicator, setShowScrollIndicator] = useState(true)
  const [atTopTimer, setAtTopTimer] = useState<number | null>(null)

  // Simulation state
  const [sigma, setSigma] = useState(15)
  const [numStrategies, setNumStrategies] = useState(3)
  const [centerBin, setCenterBin] = useState(35)
  const [strategies, setStrategies] = useState<Strategy[]>([])
  const [animationProgress, setAnimationProgress] = useState(1)
  const [isAnimating, setIsAnimating] = useState(false)
  const [r2Score, setR2Score] = useState(0)

  // Q&A state - first one open by default
  const [qaItems, setQaItems] = useState<QAItem[]>([
    {
      question: "What distributions can Algora optimize?",
      answer: "Algora supports Gaussian (bell curve), uniform, and custom distributions. You can specify any target shape by defining the liquidity weight for each price bin.",
      isOpen: true
    },
    {
      question: "How does the greedy optimization work?",
      answer: "Algora generates ~6,000 strategy templates using Spot, Curve, and BidAsk shapes. It then uses NNLS (Non-Negative Least Squares) to find optimal weights, followed by greedy forward selection to reduce to your desired number of strategies.",
      isOpen: false
    },
    {
      question: "What are Spot, Curve, and BidAsk strategies?",
      answer: "Spot distributes liquidity uniformly (flat rectangle). Curve creates a bell-shaped distribution (sine wave). BidAsk concentrates liquidity at the edges with less in the middle (V-shape). These are Meteora's native strategy templates.",
      isOpen: false
    },
    {
      question: "How accurate is the optimization?",
      answer: "Algora achieves R² > 0.99 for most distributions using just 3 strategies. This means the combined strategies match your target distribution with 99%+ accuracy.",
      isOpen: false
    },
    {
      question: "Can I deploy directly to Solana?",
      answer: "Yes! Algora exports optimized strategy plans as JSON that can be deployed directly to Meteora DLMM pools on Solana using the included TypeScript executor.",
      isOpen: false
    }
  ])

  const canvasRef = useRef<HTMLCanvasElement>(null)
  const numBins = 69

  // Smooth scroll with easing
  const smoothScrollTo = (targetId: string) => {
    const element = document.getElementById(targetId)
    if (!element) return

    const targetPosition = element.getBoundingClientRect().top + window.pageYOffset - 20
    const startPosition = window.pageYOffset
    const distance = targetPosition - startPosition
    const duration = 1000
    let start: number | null = null

    const easeInOutCubic = (t: number): number => {
      return t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2
    }

    const animation = (currentTime: number) => {
      if (start === null) start = currentTime
      const timeElapsed = currentTime - start
      const progress = Math.min(timeElapsed / duration, 1)
      const ease = easeInOutCubic(progress)

      window.scrollTo(0, startPosition + distance * ease)

      if (timeElapsed < duration) {
        requestAnimationFrame(animation)
      }
    }

    requestAnimationFrame(animation)
  }

  const handleNavClick = (e: React.MouseEvent<HTMLAnchorElement>, targetId: string) => {
    e.preventDefault()
    smoothScrollTo(targetId)
  }

  const toggleQA = (index: number) => {
    setQaItems(items => items.map((item, i) =>
      i === index ? { ...item, isOpen: true } : { ...item, isOpen: false }
    ))
  }

  // Scroll indicator logic
  useEffect(() => {
    const handleScroll = () => {
      const scrollY = window.scrollY

      if (scrollY > 10) {
        setShowScrollIndicator(false)
        if (atTopTimer) {
          clearTimeout(atTopTimer)
          setAtTopTimer(null)
        }
      } else {
        if (!atTopTimer && !showScrollIndicator) {
          const timer = window.setTimeout(() => {
            setShowScrollIndicator(true)
            setAtTopTimer(null)
          }, 1000)
          setAtTopTimer(timer)
        }
      }
    }

    window.addEventListener('scroll', handleScroll)
    return () => {
      window.removeEventListener('scroll', handleScroll)
      if (atTopTimer) clearTimeout(atTopTimer)
    }
  }, [atTopTimer, showScrollIndicator])

  // Generate target and optimize
  const runOptimization = useCallback(() => {
    const target: number[] = []
    for (let i = 0; i < numBins; i++) {
      target.push(gaussian(i, centerBin, sigma))
    }

    const newStrategies = optimizeStrategies(target, numStrategies, centerBin)
    setStrategies(newStrategies)

    // Calculate combined prediction
    const predicted = new Array(numBins).fill(0)
    for (const strategy of newStrategies) {
      for (let x = 0; x < numBins; x++) {
        predicted[x] += strategyShape(x, strategy)
      }
    }

    setR2Score(calculateR2(target, predicted))

    // Trigger animation
    setAnimationProgress(0)
    setIsAnimating(true)
  }, [sigma, numStrategies, centerBin])

  // Initial optimization
  useEffect(() => {
    runOptimization()
  }, [])

  // Animation loop
  useEffect(() => {
    if (!isAnimating) return

    const duration = 1500
    const startTime = Date.now()

    const animate = () => {
      const elapsed = Date.now() - startTime
      const progress = Math.min(elapsed / duration, 1)
      setAnimationProgress(progress)

      if (progress < 1) {
        requestAnimationFrame(animate)
      } else {
        setAnimationProgress(1)
        setIsAnimating(false)
      }
    }

    requestAnimationFrame(animate)
  }, [isAnimating])

  // Draw chart
  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return

    const ctx = canvas.getContext('2d')
    if (!ctx) return

    const dpr = window.devicePixelRatio || 1
    const rect = canvas.getBoundingClientRect()

    canvas.width = rect.width * dpr
    canvas.height = rect.height * dpr
    ctx.scale(dpr, dpr)

    const width = rect.width
    const height = rect.height
    const padding = { top: 20, right: 20, bottom: 40, left: 50 }
    const chartWidth = width - padding.left - padding.right
    const chartHeight = height - padding.top - padding.bottom

    // Clear
    ctx.fillStyle = '#E8E2D5'
    ctx.fillRect(0, 0, width, height)

    // Generate target Gaussian
    const target: number[] = []
    for (let i = 0; i < numBins; i++) {
      target.push(gaussian(i, centerBin, sigma))
    }
    const maxTarget = Math.max(...target)

    // Draw grid
    ctx.strokeStyle = 'rgba(1, 1, 31, 0.1)'
    ctx.lineWidth = 1
    for (let i = 0; i <= 4; i++) {
      const y = padding.top + (chartHeight / 4) * i
      ctx.beginPath()
      ctx.moveTo(padding.left, y)
      ctx.lineTo(width - padding.right, y)
      ctx.stroke()
    }

    // Draw axes
    ctx.strokeStyle = 'rgba(1, 1, 31, 0.3)'
    ctx.lineWidth = 1
    ctx.beginPath()
    ctx.moveTo(padding.left, height - padding.bottom)
    ctx.lineTo(width - padding.right, height - padding.bottom)
    ctx.stroke()

    // Axis labels
    ctx.fillStyle = 'rgba(1, 1, 31, 0.5)'
    ctx.font = '10px Space Grotesk'
    ctx.textAlign = 'center'
    ctx.fillText('Price Bins', width / 2, height - 8)

    ctx.save()
    ctx.translate(12, height / 2)
    ctx.rotate(-Math.PI / 2)
    ctx.fillText('Liquidity', 0, 0)
    ctx.restore()

    const binWidth = chartWidth / numBins

    // Calculate combined prediction at each bin for all strategies
    const combined: number[] = new Array(numBins).fill(0)

    // Calculate individual contributions with animation
    const strategyContributions: number[][] = strategies.map(() => new Array(numBins).fill(0))

    for (let s = 0; s < strategies.length; s++) {
      const strategyStartTime = s / strategies.length
      const strategyEndTime = (s + 1) / strategies.length
      let strategyProgress = 0

      if (animationProgress >= strategyEndTime) {
        strategyProgress = 1
      } else if (animationProgress > strategyStartTime) {
        strategyProgress = (animationProgress - strategyStartTime) / (strategyEndTime - strategyStartTime)
      }

      for (let i = 0; i < numBins; i++) {
        strategyContributions[s][i] = strategyShape(i, strategies[s]) * strategyProgress
        combined[i] += strategyContributions[s][i]
      }
    }

    // Draw combined result as filled area
    const maxCombined = Math.max(...combined, ...target)

    // Draw each strategy as a stacked colored bar for each bin
    for (let i = 0; i < numBins; i++) {
      const x = padding.left + i * binWidth
      let currentY = height - padding.bottom

      for (let s = 0; s < strategies.length; s++) {
        const contribution = strategyContributions[s][i]
        if (contribution <= 0) continue

        const barHeight = (contribution / maxCombined) * chartHeight * 0.9

        ctx.fillStyle = strategies[s].color + '80'
        ctx.fillRect(x, currentY - barHeight, binWidth - 1, barHeight)

        currentY -= barHeight
      }
    }

    // Draw outline of combined shape
    ctx.strokeStyle = '#5B8A72'
    ctx.lineWidth = 2
    ctx.beginPath()
    for (let i = 0; i < numBins; i++) {
      const x = padding.left + (i + 0.5) * binWidth
      const y = height - padding.bottom - (combined[i] / maxCombined) * chartHeight * 0.9
      if (i === 0) ctx.moveTo(x, y)
      else ctx.lineTo(x, y)
    }
    ctx.stroke()

    // Draw target Gaussian curve
    ctx.strokeStyle = '#01011F'
    ctx.lineWidth = 2
    ctx.setLineDash([5, 5])
    ctx.beginPath()

    for (let i = 0; i < numBins; i++) {
      const x = padding.left + (i + 0.5) * binWidth
      const y = height - padding.bottom - (target[i] / maxTarget) * chartHeight * 0.9

      if (i === 0) ctx.moveTo(x, y)
      else ctx.lineTo(x, y)
    }

    ctx.stroke()
    ctx.setLineDash([])

  }, [strategies, animationProgress, sigma, centerBin])

  return (
    <div className="min-h-screen">
      {/* Hero Section - Full Viewport */}
      <section className="hero-section min-h-screen flex flex-col relative">
        {/* Header */}
        <header className="w-full py-4 px-6 relative z-20">
          <div className="max-w-6xl mx-auto flex items-center justify-between">
            {/* Logo/Title */}
            <h1 className="font-display text-xl font-bold tracking-wide text-[#01011F]">
              Algora Network
            </h1>

            {/* Center Navigation */}
            <nav className="flex items-center gap-8">
              <a
                href="#what"
                className="nav-link text-sm font-medium"
                onClick={(e) => handleNavClick(e, 'what')}
              >
                What is Algora?
              </a>
              <a
                href="#how"
                className="nav-link text-sm font-medium"
                onClick={(e) => handleNavClick(e, 'how')}
              >
                How it works?
              </a>
              <a
                href="#access"
                className="nav-link text-sm font-medium"
                onClick={(e) => handleNavClick(e, 'access')}
              >
                Benefits
              </a>
            </nav>

            {/* Access Button - smaller and more margin from edge */}
            <div className="mr-4">
              <button className="btn-access px-5 py-1.5 rounded-full text-xs font-medium">
                Gain Access
              </button>
            </div>
          </div>
        </header>

        {/* Main Content - shifted up */}
        <main className="flex-1 flex items-center justify-center px-6 -mt-24 relative z-10">
          <section className="text-center max-w-4xl">
            <h2 className="font-serif-classic text-5xl md:text-6xl lg:text-7xl font-medium text-[#01011F] leading-tight">
              Precision liquidity positioning for Meteora{' '}
              <span className="dlmm-highlight">
                DLMM
                <span className="dlmm-tooltip">
                  A DLMM on Solana is a liquidity model where LPs place funds into discrete price bins for more efficient liquidity use.
                </span>
              </span>
            </h2>
            <p className="font-display text-base md:text-lg font-semibold text-[#01011F] opacity-70 mt-8 max-w-2xl mx-auto tracking-wide">
              The first open-source optimization engine for Meteora DLMM with 99%+ accuracy—no guesswork, just math.
            </p>
          </section>
        </main>

        {/* Scroll Indicator */}
        <div className={`scroll-indicator ${showScrollIndicator ? '' : 'hidden'}`}>
          <div className="scroll-arrow left">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M7 13l5 5 5-5M7 6l5 5 5-5" />
            </svg>
          </div>
          <span>Scroll to see more</span>
          <div className="scroll-arrow right">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M7 13l5 5 5-5M7 6l5 5 5-5" />
            </svg>
          </div>
        </div>
      </section>

      {/* What is Algora Section */}
      <section id="what" className="second-section min-h-screen flex items-start px-6 py-16">
        <div className="max-w-5xl mx-auto w-full">
          <div className="section-fade-in">
            <h3 className="font-serif-classic text-4xl md:text-5xl font-medium text-[#01011F] mb-12 text-left">
              What is Algora?
            </h3>

            <div className="grid md:grid-cols-2 gap-12 items-center">
              <div className="space-y-6">
                <p className="font-display text-lg text-[#01011F] opacity-80 leading-relaxed">
                  Algora is an open-source optimization engine that transforms how liquidity providers interact with Meteora's DLMM protocol.
                </p>
                <p className="font-display text-lg text-[#01011F] opacity-80 leading-relaxed">
                  Instead of manually configuring liquidity positions, Algora automatically finds the optimal combination of Meteora's strategy templates to match your desired distribution.
                </p>
                <p className="font-display text-lg text-[#01011F] opacity-80 leading-relaxed">
                  Using advanced numerical optimization (NNLS + greedy selection), it achieves <span className="font-semibold">99%+ accuracy</span> with just 3 strategies.
                </p>
              </div>

              <div className="feature-cards space-y-4">
                <div className="feature-card bg-[#F5F1E8] p-6 rounded-lg border border-[#01011F]/10">
                  <div className="flex items-start gap-4">
                    <div className="w-10 h-10 rounded-full bg-[#5B8A72]/20 flex items-center justify-center flex-shrink-0">
                      <svg className="w-5 h-5 text-[#5B8A72]" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
                      </svg>
                    </div>
                    <div>
                      <h4 className="font-display font-semibold text-[#01011F] mb-1">Precision Optimization</h4>
                      <p className="font-display text-sm text-[#01011F]/70">R² &gt; 0.99 for most distributions using only 3 strategies</p>
                    </div>
                  </div>
                </div>

                <div className="feature-card bg-[#F5F1E8] p-6 rounded-lg border border-[#01011F]/10">
                  <div className="flex items-start gap-4">
                    <div className="w-10 h-10 rounded-full bg-[#8B6B5B]/20 flex items-center justify-center flex-shrink-0">
                      <svg className="w-5 h-5 text-[#8B6B5B]" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4" />
                      </svg>
                    </div>
                    <div>
                      <h4 className="font-display font-semibold text-[#01011F] mb-1">Open Source</h4>
                      <p className="font-display text-sm text-[#01011F]/70">Fully transparent algorithms you can audit and extend</p>
                    </div>
                  </div>
                </div>

                <div className="feature-card bg-[#F5F1E8] p-6 rounded-lg border border-[#01011F]/10">
                  <div className="flex items-start gap-4">
                    <div className="w-10 h-10 rounded-full bg-[#6B5B8A]/20 flex items-center justify-center flex-shrink-0">
                      <svg className="w-5 h-5 text-[#6B5B8A]" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
                      </svg>
                    </div>
                    <div>
                      <h4 className="font-display font-semibold text-[#01011F] mb-1">One-Click Deploy</h4>
                      <p className="font-display text-sm text-[#01011F]/70">Generate and deploy optimized strategies directly to Solana</p>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* How it Works Section */}
      <section id="how" className="third-section min-h-screen px-6 py-16">
        <div className="max-w-6xl mx-auto">
          <div className="section-fade-in">
            <h3 className="font-serif-classic text-4xl md:text-5xl font-medium text-[#01011F] mb-6 text-left">
              How it works
            </h3>
            <p className="font-display text-lg text-[#01011F] opacity-70 text-left mb-16 max-w-2xl">
              Algora combines multiple Meteora strategy templates to approximate any target liquidity distribution with mathematical precision.
            </p>

            <div className="grid lg:grid-cols-2 gap-12 items-start">
              {/* Q&A Dropdowns */}
              <div className="space-y-3">
                {qaItems.map((item, index) => (
                  <div
                    key={index}
                    className="qa-item bg-[#F5F1E8] rounded-lg border border-[#01011F]/10 overflow-hidden"
                  >
                    <button
                      onClick={() => toggleQA(index)}
                      className="w-full px-5 py-4 flex items-center justify-between text-left hover:bg-[#01011F]/03 transition-colors"
                    >
                      <span className="font-display font-medium text-[#01011F] text-sm">
                        {item.question}
                      </span>
                      <svg
                        className={`w-4 h-4 text-[#01011F]/50 transition-transform duration-300 ${item.isOpen ? 'rotate-180' : ''}`}
                        fill="none"
                        viewBox="0 0 24 24"
                        stroke="currentColor"
                      >
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                      </svg>
                    </button>
                    <div
                      className={`qa-answer overflow-hidden transition-all duration-300 ${item.isOpen ? 'max-h-48 opacity-100' : 'max-h-0 opacity-0'}`}
                    >
                      <p className="px-5 pb-4 font-display text-sm text-[#01011F]/70 leading-relaxed">
                        {item.answer}
                      </p>
                    </div>
                  </div>
                ))}
              </div>

              {/* Interactive Simulation */}
              <div className="simulation-container bg-[#E8E2D5] rounded-xl p-6 border border-[#01011F]/10">
                <div className="flex items-center justify-between mb-6">
                  <h4 className="font-display font-semibold text-[#01011F]">Live Simulation</h4>
                  <div className="flex items-center gap-2">
                    <span className="font-display text-xs text-[#01011F]/60">R² Score:</span>
                    <span className="font-display text-sm font-bold text-[#5B8A72]">
                      {(r2Score * 100).toFixed(1)}%
                    </span>
                  </div>
                </div>

                {/* Controls */}
                <div className="grid grid-cols-3 gap-4 mb-6">
                  <div className="input-group">
                    <label className="font-display text-xs text-[#01011F]/60 block mb-2">
                      Sigma (Spread)
                    </label>
                    <input
                      type="range"
                      min="5"
                      max="25"
                      value={sigma}
                      onChange={(e) => setSigma(Number(e.target.value))}
                      className="input-range w-full"
                    />
                    <span className="font-display text-xs text-[#01011F]/80 mt-1 block text-center">{sigma}</span>
                  </div>

                  <div className="input-group">
                    <label className="font-display text-xs text-[#01011F]/60 block mb-2">
                      Center Bin
                    </label>
                    <input
                      type="range"
                      min="20"
                      max="50"
                      value={centerBin}
                      onChange={(e) => setCenterBin(Number(e.target.value))}
                      className="input-range w-full"
                    />
                    <span className="font-display text-xs text-[#01011F]/80 mt-1 block text-center">{centerBin}</span>
                  </div>

                  <div className="input-group">
                    <label className="font-display text-xs text-[#01011F]/60 block mb-2">
                      Strategies
                    </label>
                    <input
                      type="range"
                      min="1"
                      max="5"
                      value={numStrategies}
                      onChange={(e) => setNumStrategies(Number(e.target.value))}
                      className="input-range w-full"
                    />
                    <span className="font-display text-xs text-[#01011F]/80 mt-1 block text-center">{numStrategies}</span>
                  </div>
                </div>

                {/* Run Button */}
                <button
                  onClick={runOptimization}
                  disabled={isAnimating}
                  className="btn-run w-full py-2 rounded-lg font-display text-sm font-medium mb-6"
                >
                  {isAnimating ? 'Optimizing...' : 'Run Optimization'}
                </button>

                {/* Chart */}
                <div className="chart-container bg-[#E8E2D5] rounded-lg overflow-hidden">
                  <canvas
                    ref={canvasRef}
                    className="w-full"
                    style={{ height: '280px' }}
                  />
                </div>

                {/* Legend */}
                <div className="flex flex-wrap gap-4 mt-4 justify-center">
                  <div className="flex items-center gap-2">
                    <div className="w-4 h-0.5 bg-[#01011F]" style={{ borderStyle: 'dashed' }}></div>
                    <span className="font-display text-xs text-[#01011F]/60">Target (Gaussian)</span>
                  </div>
                  {strategies.map((s, i) => (
                    <div key={i} className="flex items-center gap-2">
                      <div className="w-4 h-3 rounded-sm" style={{ backgroundColor: s.color + '60' }}></div>
                      <span className="font-display text-xs text-[#01011F]/60 capitalize">
                        {s.type === 'bidask' ? 'Bid-Ask' : s.type.charAt(0).toUpperCase() + s.type.slice(1)}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>
    </div>
  )
}

export default App
