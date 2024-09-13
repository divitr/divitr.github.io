import React from 'react';
import './About.css';
import AboutImage from './imgs/about_img.png';
import { FaLinkedin } from 'react-icons/fa';

const About = () => {
  return (
    <div className="about-container">
      <h2>About Me</h2>
      <div className="ab-content">
        <div className="about-image">
          <img src={AboutImage} alt="About me" />
        </div>
        <div className="about-text">
          <p>I'm a sophomore at UC Berkeley, studying Physics, Mathematics, and Electrical Engineering and Computer Science (minor).</p>
          <p>My interests lie at the intersection of computer science, mathematics, and physics, and I especially enjoy modeling and predicting physical systems using tools from machine learning and statistical mechanics. </p>
          <div className="button-container">
            <a href="https://github.com/divitr/resume_auto_update/blob/main/physics/Divit_Rawal.pdf" target="_blank" className="project-button">
              <span>Resume</span>
            </a>
            <a href="https://www.linkedin.com/in/divit-rawal" target="_blank" className="project-button">
              <span><FaLinkedin/> LinkedIn</span>
            </a>
          </div>
        </div>
      </div>
    </div>
  );
}

export default About;
