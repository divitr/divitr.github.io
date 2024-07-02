// App.js
import React from 'react';
import {Route, Routes } from 'react-router-dom';
import Header from './Header';
import Home from './Home';
import About from './About';
import Education from './Education';
import Research from './Research';
import Projects from './Projects';
import ProjectPage from './ProjectPage';
import ResearchPage from './ResarchPage';
import './App.css';

import OpenSearchLogo from './imgs/opensearch_logo.png';
import BurnInGraph from './imgs/mcmc_burnin.png';
import ReseDemo from './imgs/rese-demo.mp4';
import Watersort1 from './imgs/ws1.png';
import Watersort2 from './imgs/ws2.png';
import Watersort3 from './imgs/ws3.png';
import AntichessGame from './imgs/antichessGame.png';

import ROCHeader from './imgs/roc_src_src.png';
import ZMasses from './imgs/Z_masses.png';

const App = () => {
  return (
      <div className="app-container">
        <Header />
        <div className="content-container">
          <Routes>
            <Route path="/" element={<Home />} />
            <Route path="/about" element={<About />} />
            <Route path="/education" element={<Education />} />
            <Route path="/research" element={<Research />} />
            <Route path="/projects" element={<Projects />} />
            <Route path="/projects/antichess" element={<ProjectPage
                      title="AntiChess Engine"
                      description="Antichess is a variant of chess in which the goal is to have all your pieces captured by your opponent. I developed a PyPI package to play single and two player antichess games. The package supports multiple strategies, including implementations of Minimax with alpha beta pruning, Monte-Carlo Tree Search, and an ε-greedy Breadth First Search."
                      githubLink="https://github.com/divitr/antichess"
                      demoContent={<img src={AntichessGame} alt="Antichess Game" style={{ maxWidth: '100%' }} />} />} />
            <Route path="/projects/opensearch" element={<ProjectPage
                      title="Amazon Opensearch"
                      description="Amazon OpenSearch is an open-source search and analytics service that helps users analyze and visualize large volumes of data in real-time. As a member of the OpenSearch Contributor Initiative, I collaborated with data engineers from around the globe to develop Machine Learning algorithms and integrations in Java."
                      githubLink="https://github.com/opensearch-project/ml-commons"
                      demoContent={<img src={OpenSearchLogo} alt="Amazon OpenSearch Logo" style={{ maxWidth: '100%' }} />} />} />
            <Route path="/projects/pdrp" element={<ProjectPage
                      title="Physics Directed Reading Program"
                      description="During Fall 2023, I was part of the UC Berkeley Physics Directed Reading Program. In this program, I was paired with a graduate student in physics and together we studied the intersection of Physics and Machine Learning. At the end of the semester, I gave a presentation on how Physics and Machine Learning motivate each other to UC Berkeley Physics undergraduate and graduate students."
                      githubLink="https://github.com/divitr/ising_mcmc"
                      demoContent={<img src={BurnInGraph} alt="MCMC Burn In Graph" style={{ maxWidth: '100%'}} />} />} />
            <Route path="/projects/research-engine" element={<ProjectPage
                      title="Research-Engine"
                      description="While working on a research project for one of my high school classes, I realized I was spending a large amount of time gathering information from various websites and papers to gain a comprehensive understanding of the subject matter. In reseponse, two friends and I set out to create Research-Engine: a website that uses the power of web scraping and natural language processing to provide an overview of a topic. Research-Engine offers users a streamlined solution by providing an overview of the desired topic, along with relevant papers and carefully curated summaries of associated websites."
                      githubLink="https://github.com/divitr/research-engine"
                      demoContent={<video src={ReseDemo} alt="Research-Engine Demo Video" controls style={{ maxWidth: '100%'}} />} />} />
            <Route path="/projects/watersort-solver" element={<ProjectPage
              title="Watersort Solver"
              description="In the pursuit of solving a particularly challenging watersort brainteaser, I developed an algorithm in Java to solve any watersort puzzle. Later, I leveraged my experience with app development using Flutter to create a mobile application on the Google Play Store. Watersort Solver allows users to interactively set up any imaginable watersort puzzle and see a step by step solution."
              githubLink="https://github.com/divitr/watersort_solver_app"
              demoContent={
                <div
                  style={{
                    display: 'flex',
                    gap: '10px',
                    maxWidth: '100%',
                    justifyContent: 'center'
                  }}
                >
                  <img style={{
                    display: 'flex',
                    gap: '10px',
                    maxWidth: '30%'
                  }} src={Watersort1} alt="Watersort Image 1" />
                  <img style={{
                    display: 'flex',
                    gap: '10px',
                    maxWidth: '30%'
                  }} src={Watersort2} alt="Watersort Image 2" />
                  <img style={{
                    display: 'flex',
                    gap: '10px',
                    maxWidth: '30%'
                  }} src={Watersort3} alt="Watersort Image 3" />
                </div>
              }
            />} />
            <Route path="/research/soft_extrapolation" element={<ResearchPage
                      title="High Momentum Collision Analysis"
                      description={<div>
                        Oftentimes, particle detectors pick up noise that hinders efforts to analyze the true data. Working with Dr. Daniel Whiteson and Dr. Aishik Ghosh at the UC Irvine Department of Physics and Astronomy, I developed neural networks to discriminate between signal and background data from detector readings. Because it is difficult to analyze high momentum collisions, training data is limited, and training machine learning models is challenging. To overcome this problem, we developed four identical models, trained them on low momentum data, and tested their ability to extrapolate to high momentum data, resulting in greater than 90% accuracy.
                      </div>}
                      githubLink="https://github.com/divitr/soft_extrap_toy"
                      demoContent={<img src={ROCHeader} alt="ROC src src" style={{ width: '100%' }} />} />} />
            <Route path="/research/particle_reconstruction" element={<ResearchPage
                title="Heavy Particle Reconstruction"
                description={<div>
                  In High-Energy Physics, particles often decay before they are recorded by detectors, making it difficult to study their properties and interactions. However, by examining the particles they decay into, the original particles can be "reconstructed", allowing us to glean information about them. With the guidance of Dr. Daniel Whiteson and Dr. Michael Fenton at the UC Irvine Department of Physics and Astronomy, I simulated particle collisions and decays and wrote algorithms in C++ and Python to reconstruct heavy particles. I focused primarily on reconstructing Z<sup>0</sup> bosons and top quarks. Using my algorithm (and a χ<sup>2</sup> method), I was able to calculate the masses of these particles to within 2% error.
                </div>}
                githubLink="https://github.com/divitr/top_recon_chisq"
                demoContent={<img src={ZMasses} alt="Z Boson Masses" style={{ width: '100%' }} />} />} />
          </Routes>
        </div>
      </div>
  );
}

export default App;
