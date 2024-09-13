import React from 'react';
import CertCard from './CertCard';
import './Education.css';

import ColumbiaLogo from './imgs/columbia_logo.png';
import IBMLogo from './imgs/ibm.png';
import GenevaLogo from './imgs/geneva_logo.png';
import StanfordLogo from './imgs/stanford_logo.png';

const projects = [
  {
    title: 'Decision Making and Reinforcement Learning',
    description: 'Principles and algorithms used to optimize decision-making processes within dynamic environments.',
    link: "https://www.coursera.org/account/accomplishments/verify/XU7H7AUXXP6J",
    githubLink: null,
    demoContent: <img src={ColumbiaLogo} alt="Columbia Logo" />
  },
  {
    title: 'Machine Learning',
    description: 'Theoretical and practical foundations of machine learning, with a focus on deep learning.',
    link: "https://www.coursera.org/account/accomplishments/professional-cert/KEEXCEXSVNTS",
    githubLink: null,
    demoContent: <img src={IBMLogo} alt="IBM Logo" />
  },
  {
    title: 'Particle Physics',
    description: 'Fundamental principles and mathematical frameworks underlying particle and nuclear physics.',
    link: "https://www.coursera.org/account/accomplishments/verify/QZGDRCQQTF8D",
    githubLink: null,
    demoContent: <img src={GenevaLogo} alt="University of Geneva Logo" />
  },
  {
    title: 'Game Theory',
    description: 'Mathematical and computational aspects of strategic decision-making in single and multi player games.',
    link: "https://www.coursera.org/account/accomplishments/verify/C7YG2R47DDYW",
    githubLink: null,
    demoContent: <img src={StanfordLogo} style={{ maxHeight: "40%"}}alt="Stanford Logo" />
  },
];

const Projects = () => {
  return (
    <div className="projects-container">
      <h2 className="projects-heading">Certifications and Courses</h2>
      <div className="projects-list">
        {projects.map((project, index) => (
          <CertCard
            key={index}
            title={project.title}
            description={project.description}
            link={project.link}
            githubLink={project.githubLink}
            demoContent={project.demoContent}
          />
        ))}
      </div>
    </div>
  );
};

export default Projects;
