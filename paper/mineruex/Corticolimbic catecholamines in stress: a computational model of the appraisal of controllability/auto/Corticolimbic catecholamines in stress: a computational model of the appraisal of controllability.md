ORIGINAL ARTICLE

# Corticolimbic catecholamines in stress: a computational model of the appraisal of controllability

Vincenzo G. Fiore • Francesco Mannella • Marco Mirolli • Emanuele Claudio Latagliata • Alessandro Valzania • Simona Cabib • Raymond J. Dolan • Stefano Puglisi-Allegra • Gianluca Baldassarre

Received: 7 October 2013 / Accepted: 4 February 2014 / Published online: 28 February 2014

- The Author(s) 2014. This article is published with open access at Springerlink.com

Abstract Appraisal of a stressful situation and the possibility to control or avoid it is thought to involve frontalcortical mechanisms. The precise mechanism underlying this appraisal and its translation into effective stress coping (the regulation of physiological and behavioural responses) are poorly understood. Here, we propose a computational model which involves tuning motivational arousal to the appraised stressing condition. The model provides a causal explanation of the shift from active to passive coping strategies, i.e. from a condition characterised by high motivational arousal, required to deal with a situation appraised as stressful, to a condition characterised by emotional and motivational withdrawal, required when the stressful situation is appraised as uncontrollable/unavoidable. The model is motivated by results acquired via microdialysis recordings in rats and highlights the presence of two competing circuits dominated by different areas of the ventromedial prefrontal cortex: these are shown having

opposite effects on several subcortical areas, affecting dopamine outflow in the striatum, and therefore controlling motivation. We start by reviewing published data supporting structure and functioning of the neural model and present the computational model itself with its essential neural mechanisms. Finally, we show the results of a new experiment, involving the condition of repeated inescapable stress, which validate most of the model’s predictions.

Keywords Dopamine - Noradrenaline - Appraisal - Chronic stress - Animal model - Cortical control

## Introduction

Stressful events (stressors) are experiences that an organism appraises as difficult to deal with by reliance on its current repertoire of physiological, behavioural, and psychological responses. An initial appraisal is required to classify an event as stressful so to trigger effective (active) coping strategies. Once these are deployed, a second appraisal establishes whether the stressor is controllable/ avoidable, hence sensitive to the organism’s reaction, or uncontrollable/unavoidable, thus requiring a shift towards a passive coping strategy aimed at conserving energy and resources (Folkman et al. 1986; Lazarus 1993; Huether et al. 1999; Ursin and Eriksen 2004; Anisman and Matheson 2005).

Converging evidence points to the frontal cortices as a key factor for the appraisal of controllability (Phan et al. 2004; Amat et al. 2005; Salomons et al. 2007; Ohira et al. 2008; Wager et al. 2008; Maier and Watkins 2010). However, the mechanisms involved in tuning behavioural and physiological stress responses are still mostly unexplored. The aim of the present paper is to propose a brain circuit that could translate stress appraisal into a motivational state sufficient for implementation of appropriate coping strategies.

Coping responses aimed at escaping, removing or controlling a condition appraised as stressful require high emotional/motivational arousal. Furthermore, if the stressor is experienced for the first time, the development of novel coping strategies requires focused, effortful and risky attempts. However, if the situation is insensitive to both previously established strategies and newly deployed ones, a rapid shift into passive coping is required in order to prevent sustained stress responses that are dangerous for the organism’s survival and well-being. Emotional/motivational withdrawal can stop physiological stress responses and terminate active coping (Cabib and Puglisi-Allegra 2012).

Mesoaccumbens dopamine (DA) is considered a key modulator of motivational arousal. High DA levels in the nucleus accumbens (NAcc) support effortful goal-seeking, whereas blockade of DA transmission in NAcc interferes with motivated behaviour (Salamone et al. 2003; Cagniard et al. 2006; Niv et al. 2007; Floresco et al. 2008). Moreover, DA transmission is involved in learning and NAcc is part of the complex circuit mediating the acquisition and control of goal-directed behaviour (Mannella et al. 2013). In stressed animals, NAcc DA levels undergo dramatic fluctuations that are controlled by catecholaminergic transmission in the ventromedial prefrontal cortex (vmPFC; Pascucci et al. 2007). Therefore, by modulating mesoaccumbens DA, vmPFC could tune the motivational state of the organism to the appraised situation.

Here, we propose a model of these processes. The paper first presents the biological bases of the model in the form of a review. This is not meant to be an exhaustive review of the neurobiological mechanisms involved in stress coping, but a selection of literature that has guided the development of a computational hypothesis explaining appraisal of controllability in terms of the neural mechanisms in both vmPFC and NAcc. Next, we introduce a system-level computational model. This model suggests the appraisal of controllability results from the interplay between two circuits dominated by different subregions in the vmPFC and supported by either cortical DA or norepinephrine (NE). This is the first integrated operational explanation of the observed phenomena and provides predictions in the form of simulations of expected catecholamine outflows, across a variety of conditions. Lastly, the paper presents new data testing the model’s core hypothesis. In particular, we establish a comparison between in vivo experiments testing the effects of repeated stress experience and relative simulated predictions. The results of these comparisons support the validity of the working hypotheses and the soundness of the approach (cf. Montague et al. 2012).

## Materials and methods

## The biology behind the model

The starting point in our model is a group of experiments using intracerebral microdialysis to analyse changes of catecholamine releases in vmPFC and NAcc of rats during their first experience with an uncontrollable/unavoidable stressor (Fig. 1). The results of these experiments revealed time-dependent changes of DA outflow in the NAcc and of NE and DA outflows in the vmPFC. In the first minutes following stress onset, NE in vmPFC and DA in NAcc increase in parallel, whereas DA in vmPFC shows a small and transitory peak. Blockade of NE transmission in vmPFC by selective depletion or by local infusion of an alpha1-adrenergic antagonist prevented the increase of DA outflow in the NAcc. In the course of the stress experience NE in vmPFC declines to reach basal levels, whereas DA outflow shows a second larger and sustained increase while at the same time DA in NAcc decreases below basal levels. The decrease of DA in NAcc below basal levels can be prevented by selective depletion of DA in vmPFC (Pascucci et al. 2007; Nicniocaill and Gratton 2007).

These results highlight that in stressed animals a causal relationship exists between increased NE release in vmPFC and increased DA outflow in NAcc, and between increased DA release in vmPFC and decreased DA outflow in NAcc. Converging evidences (reviewed in Cabib and Puglisi-Allegra 2012) support the view that enhanced DA outflow in NAcc is associated with expression of active coping strategies aimed at removing/avoiding the source of stress, whereas decrease of DA release below basal level is associated with expression of passive coping in unavoidable/uncontrollable stressful situation. Moreover, there is evidence supporting the view that either the large increase of DA in vmPFC or the decrease of DA in NAcc are selectively promoted by experiences appraised as uncontrollable/unavoidable (Bland et al. 2003a; Cabib and Puglisi-Allegra 1994). Therefore, the changes of catecholamine levels in the vmPFC and in NAcc that characterise the response to a novel unavoidable/uncontrollable stressor could derive from the primary appraisal of the stressfulness of a stimulus and the subsequent appraisal of its uncontrollability.

![](images/1d018262d46dcccddff8eddac0d8f3e4d82347526f23c094c42bec51b24f8707.jpg)

![](images/9e4736e9882a37f2d1a8331383f5b375f2e8ad06ed55de58133a58514f8a0063.jpg)

![](images/ab412e7c15b446d999d2bb41381a5fe32862b2b8ceda0d49b87d4b2a057db731.jpg)  
Fig. 1 Release of NE (a) and DA (b) measured in the vmPFC, and DA measured in NAcc (c). Data recorded during a restraint experiment lasting 240 min and run in three different conditions:

Catecholamines collected by intracerebral microdialysis derive from specific populations of projecting neurons. vmPFC NE derives from locus coeruleus (LC), part of a vast and diffuse system arising from a small population of noradrenergic cells (Glavin 1985; Aston-Jones et al. 1999; Valentino and Van Bockstaele 2001; Berridge and Waterhouse 2003). LC receives strong convergent projections from orbito-frontal cortex (OFC), anterior cingulate cortex (ACC), and central nucleus of the amygdala (Amg), a major node of the central Amg (CeA). Converging OFC and ACC inputs to LC are thought to drive transitions between phasic and tonic modes in NE neurons to fit behavioural/cognitive states with perceived environmental conditions (Aston-Jones and Cohen 2005), whereas a direct input from the CeA modulates LC neuronal activity through excitatory inputs (Van Bockstaele et al. 2001; Curtis et al. 2002; Bouret et al. 2003; Jedema and Grace 2004). Stress promotes an increase of vmPFC NE levels that exceeds those required to support cognitive functions and leads to a selective activation of alpha1 adrenergic receptors (Arnsten 2009) that indirectly stimulates DA release in NAcc (Nicniocaill and Gratton 2007).

Stress-induced changes in DA levels appear to involve mainly VTA projecting cells (Abercrombie et al. 1989; Kalivas and Duffy 1995; Barrot et al. 1999; Inglis and sham, depletion of vmPFC NE, and depletion of vmPFC DA. Reprinted from Pascucci et al. (2007), by permission of Oxford Univeristy Press.

Moghaddam 1999; Barrot et al. 2000). These cells project toward the vmPFC as well as to the NAcc; however, these areas receive inputs from different populations of DA cells controlled by different and largely independent circuits (Carr and Sesack 2000; Margolis et al. 2006; Briand et al. 2007; Lammel et al. 2008). In particular, they receive different afferent projections from the vmPFC (Room et al. 1985; Carr and Sesack 2000; Jackson et al. 2001).

Stress-induced changes of DA levels are slow and detectable by intracerebral microdialysis (Cabib and Puglisi-Allegra 2012, for a review). This suggests that stress-induced increased DA levels depend on the removal of inhibitory constraints influencing the number of spontaneously active VTA neurons (‘‘tonically’’ active neurons; Floresco et al. 2003; Grace et al. 2007) rather than on an increase in fastspiking activity of already active neurons (phasic activity). VTA receives inhibitory inputs from the CeA which leads to an increase of NAcc DA (Ahn and Phillips 2003), suggesting that this input is part of a double inhibition mechanism (Fudge and Haber 2000; Ahn and Phillips 2002; Fudge and Emiliano 2003; Floresco et al. 2003). Therefore, CeA seems to play a major role in the promotion of an initial response to stress by corticolimbic catecholamines, in line with its involvement in emotional and behavioural stress responses (Koob 2009) and in the regulation of various neuromodulatory systems (Mirolli et al. 2010), in particular in stressful conditions (Davis and Whalen 2001).

A group of brain areas classically associated with physiological and behavioural (especially innate) responses to stressors, namely the hypothalamus, periaqueductal gray, and dorsal raphe nucleus (DR; Keay and Bandler 2001; Herman et al. 2005; Maier and Watkins 2005) are also linked to the functions of DA neurons in the VTA (Geisler et al. 2007; Rodaros et al. 2007; Omelchenko and

Sesack 2010; Watabe-Uchida et al. 2012). In particular, increased serotonin (5-HT) release is correlated with increased cortical DA outflow in the condition of inescapable stress (Bland et al. 2003a), indicating that neural activity of VTA cell populations responsible for cortical DA release and DR activity (responsible for the 5-HT release) are themselves tightly correlated.

Finally, as already pointed out, frontal cortices are the major sources of both primary and secondary appraisal. The appraisal of a situation as stressful is based on the available information about the external environment and the organism’s physiological and psychological state (Folkman et al. 1986; Lazarus 1993). OFC and the ACC, involved in emotional appraisal and stress perception (Pruessner et al. 2008) can be an important source of information for CeA output, but vmPFC could play a major role in appraisal through the interplay between its two major components: the infralimbic (IL) and prelimbic (PL) cortices.

First, it has been demonstrated that PL constrains, whereas IL facilitates, classic physiological stress responses (Diorio et al. 1993; Sullivan and Gratton 2002; Radley et al. 2006; Tavares et al. 2009), a role also mediated by their opposing effect in controlling the activity of the DR (Radley et al. 2009). Second, results of lesion studies suggest these cortices are involved in behavioural flexibility via attentional selection (Delatour and Gisquet-Verrier 2000) and adaptation to new contingencies (Gisquet-Verrier and Delatour 2006). Moreover, PL enhances whereas IL inhibits fear reaction (Vidal-Gonzalez et al. 2006; Peters et al. 2009; Sotres-Bayon and Quirk 2010). Third, PL is involved in action-outcome learning and goal-directed behaviour expression, whereas IL is involved in switching to a stimulus–response behavioural mode (Balleine and Dickinson 1998; Coutureau and Killcross 2003; Killcross and Coutureau 2003). Finally, PL excites CeA output neurons, whereas IL inhibits them through the activation of GAB-Aergic neurons, located in the intercalated nuclei (ITC) of the Amg (Vidal-Gonzalez et al. 2006; Peters et al. 2009).

## The computational model: core hypotheses and mechanisms

The complex neural circuitry and mechanisms underlying an appraisal of stress controllability can be exploited to provide a causal explanation of the phenomenon itself. Here, we design a system-level model (Baldassarre et al. 2013; Fiore et al. 2014) involving a rather large number of neural systems and two neuromodulators, DA and NE: Fig. 2 shows the functional components of the model and the main relationships among them. The detailed circuitry of the model, which has been implemented in Matlab, is shown in Fig. 3.

The model relies on one pivotal hypothesis about the role played by PL and IL in uncontrollable stress conditions. In short, it is useful to distinguish three phases. First, PLdominated circuitry, supported by NE regulation, leads active coping via the expression of goal-directed behaviour after a primary appraisal (evaluation of the presence of a stressor). Second, PL–IL interplay contributes in realising the second appraisal (evaluation of controllability of the stressor) determining the switch from the active phase to the passive one. Finally, IL-dominated circuitry, supported by cortical DA regulation, exerts control over activity of PL and various subcortical areas, causing low DA outflow in the NAcc and maintaining passive coping.

![](images/795a08a75f16d77778d5db68bc63d82bf9de13348dd1ecad6a19a4bd5b9faf9a.jpg)  
Fig. 2 Functional representation of the architecture. This simplified representation shows the net excitatory/inhibitory influence that each component has on the target components. The text in the boxes indicates the main functional role played by each component in realising the stress responses

Besides the constraints deriving from the connectivity described in the previous section (see also Table 1 for full references), it is important to point out a few other features characterising the architecture and the functioning of the present model.

The inescapable stressor is represented by a constant input signal starting 20 min after the beginning of the simulation. Information about the stressful condition has four different targets: OFC/ACC, vmPFC, CeA and DR. Consistent with described literature about neuromodulator dynamics and effects, the decoupled dynamics of vmPFC DA and NAcc DA are simulated by splitting the VTA into two separate modules, respectively, mesocortical VTA (mcVTA) and mesolimbic VTA (mlVTA). These are characterised by different afferent and efferent connectivity but share the same DA-dependent effects on their respective targets. By contrast, LC is represented by a single component causing the simulated NE release, but this neuromodulator has different effects depending on its target areas, reproducing the inhomogeneous distribution of alpha receptors (Briand et al. 2007; Arnsten 2009): the model assumes NE has an excitatory value on the vmPFC population of neurons connected to Amg and DR and an inhibitory effect on the vmPFC population of neurons connected to VTA. Finally, early simulations have driven the hypothesis that projections from DR to VTA may be asymmetrical, favouring the mcVTA module: we will discuss below how this hypothesis impacts the dynamics of the system in a relevant way.

Fig. 3 Neural architecture of the model showing its components and subcomponents (rounded square areas), their neural assemblies (circles), and their connections (links). The size of circles and links, respectively, encode the degree of activity of neural assemblies and the strength of the signals transmitted between them. The first phase (left, active response) and second phase (right, passive response) refer to the activity recorded in the sham condition  
![](images/44a903be82c22ac132f3560cab98a17de75b568ab2291ca013b1a8686551f813.jpg)

The slow dynamics allow the use of leaky neural units (Dayan and Abbott 2001) as a building block (Baldassarre et al. 2013; Fiore et al. 2014). Therefore, each unit of the model simulates the activity of a whole neural population in a way that resembles mean field potential recordings (Bojak et al. 2003):

$$
\begin{array} { l } { { \displaystyle \tau _ { j } \dot { u } _ { j } = - u _ { j } + b _ { j } + \sum _ { i } w _ { j i } a _ { i } } } \\ { ~ } \\ { { \displaystyle a _ { j } = \left[ \operatorname { t a n h } \left( u _ { j } \right) \right] + } } \end{array}\tag{ð1Þ}
$$

where $\tau _ { j }$ is the time constant, $u _ { j }$ is the action potential and $b _ { j }$ is the baseline activation of the unit $j . \sum _ { i } \left[ w _ { j i } a _ { i } \right]$ represents the sum of all products between each single input $a _ { i }$ reaching j and the corresponding synaptic strength $w _ { j i } .$ Finally, [.]? is a function returning its argument if this is positive and zero if it is negative, and tanh[.] is the hyperbolic tangent function used as a positive saturation transfer function.

![](images/4066a64a4ecbb4d1b8ace57f7b266ad64031ed12ba561ab4e244913ff29843e8.jpg)

The slow accumulation and reuptake of the neuromodulators in the extrasynaptic space is simulated by relying on the following equation:

$$
\tau _ { n k } \dot { l } _ { n k } = - ( t h _ { n k } \ \operatorname { t a n h } [ l _ { n k } ] ) \ + \ w _ { n k } a _ { n }\tag{ð2Þ}
$$

Compared to the standard equation of the leaky integrator (Eq. 1), this modified version adds a reuptake capacity of the target area k. When the level of the neuromodulator $l _ { n k }$ drops below a threshold representing the overall reuptake capacity of the system $( t h _ { n k } ) ,$ the injection of the neuromodulator $w _ { n k } a _ { n }$ and its reuptake $- ( t h _ { n k } \mathrm { t a n h } [ l _ { n k } ] )$ compensate and $l _ { n k }$ reaches an equilibrium; conversely, when it exceeds the threshold, the level of the neuromodulator starts to increase progressively (see Fellous and Linster 1998 for several ways of modelling these phenomena).

To perform the simulated depletions, we introduced a dynamic coefficient affecting the input in Eq. $2 \colon ( 1 - d _ { n k } )$ $( w _ { n k } a _ { n } )$ . When simulating the depletions of either DA or NE, the value of $d _ { n k }$ slowly grows in the range [0–1], lowering the amount of neuromodulator released. The regulation of $d _ { n k }$ towards the desired level $d _ { n k } ^ { \prime }$ is determined by the following equation:

Table 1 List of key references supporting the connectivity of the model
<table><tr><td>Dopamine in NAcc Dopamine in vmPFC</td><td>Joel and Weiner (1997) Zhou and Hablitz (1999)</td></tr><tr><td rowspan="4">IL-PL interplay</td><td>Lewis and O&#x27;Donnell (2000)</td></tr><tr><td>Tierney et al. (2008)</td></tr><tr><td>Coutureau and Killcross (2003)</td></tr><tr><td>Vertes (2004)</td></tr><tr><td rowspan="5">vmPFC efferents to the VTA</td><td>Quirk and Mueller (2008)</td></tr><tr><td>Sotres-Bayon and Quirk (2010)</td></tr><tr><td>Room et al. (1985)</td></tr><tr><td>Carr and Sesack (2000)</td></tr><tr><td>Vertes (2004)</td></tr><tr><td rowspan="3">vmPFC differential control over CeA and ITC in the Amg</td><td>Radley et al. (2009)</td></tr><tr><td>Vertes (2004)</td></tr><tr><td>Vidal-Gonzalez et al. (2006)</td></tr><tr><td rowspan="3">DR efferents to the VTA</td><td>Vertes (1991)</td></tr><tr><td>Geisler et al. (2007)</td></tr><tr><td>Rodaros et al. (2007)</td></tr><tr><td rowspan="3">CeA efferents to the mesolimbic VTA</td><td>Fudge and Haber (2000)</td></tr><tr><td>Ahn and Phillips (2002)</td></tr><tr><td>Fudge and Emiliano (2003)</td></tr><tr><td rowspan="3">OFC-ACC efferents to the LC CeA efferents to the LC</td><td>Aston-Jones and Cohen (2005)</td></tr><tr><td>Curtis et al. (2002)</td></tr><tr><td>Berridge and Waterhouse (2003)</td></tr></table>

$$
\tau _ { d _ { n k } } \dot { d } _ { n k } = - d _ { n k } + d _ { n k } ^ { \prime }\tag{ð3Þ}
$$

Both DA and NE activate metabotropic receptors within neurons of target areas: these receptors are involved in a range of second messenger chemical reactions. This effect is twofold: first, the metabolic status of the target neurons changes, either increasing or decreasing the chances that any incoming signal has to produce post-synaptic action potentials (i.e. the flow of ions such as Na?, $\bar { \mathrm { K } ^ { + } } , \bar { \mathrm { C a } ^ { 2 + } }$ or Cl- becomes more or less effective, depending on the activated receptor). Secondly, the presence of a neuromodulator may also result in opening new ion channels, becoming itself part of the incoming stimulus (Missale et al. 1998; Chidlow et al. 2000).

Leaky equations simulate the flow of ions as an either positive or negative numerical input for each unit, therefore neuromodulators are commonly simulated relying on multiplicative effects modulating the input (Fellous and Linster 1998). These effects consist in either strengthening or weakening the input generated by other neural units (multiplying or dividing it). In addition, the present model also gives an account of the opening of new ion channels caused by the presence of the neuromodulators, which are then considered as a (minor) direct input for each target unit: these are the additive effects. In this respect, Eq. 1 is modified as follows:

$$
\begin{array} { c } { { \tau _ { j } \dot { u } _ { j } = - u _ { j } + \left( b _ { j } + \displaystyle \sum _ { i } \left[ w _ { j i } a _ { i } \right] \right) ~ \displaystyle \frac { 1 + \sum \left[ \mu _ { e l k } l _ { k } \right] } { 1 + \sum \left[ \mu _ { d l k } l _ { k } \right] } } } \\ { { + ~ \displaystyle \sum \left[ \alpha _ { e l k } l _ { k } \right] - \sum \left[ \alpha _ { d l k } l _ { k } \right] } } \end{array}\tag{ð4Þ}
$$

where the coefficients $\mu _ { e l k }$ and $\alpha _ { e l k }$ regulate respectively the multiplicative excitatory and additive excitatory effects of the neuromodulator l on target area $k ,$ whereas the coefficients $\mu _ { d l k }$ and $\alpha _ { d l k }$ regulate respectively the multiplicative inhibitory and additive inhibitory effects of the neuromodulator l on the same area. Note that the multiplicative effects depend on the size of the local glutammaergic/ GABAergic signals, whereas the additive ones are independent of them.

Finally, the Hebbian learning processes leading to the increase in the strength of internal connections of vmPFC are implemented using the following learning rule:

$$
w _ { j i } [ t ] = w _ { j i } [ t - 1 ] + \eta \left[ a _ { j } - t h _ { j } \right] ^ { + } [ a _ { i } - t h _ { i } ] ^ { + }\tag{ð5Þ}
$$

where $w _ { j i } [ t ]$ is the connection weight between unit i and unit j (at time t), g is a learning rate, and $\mathrm { t h } _ { j }$ and thi are the thresholds that the activations of $a _ { j }$ and $a _ { i }$ have to overcome in order to trigger the learning process.

A genetic algorithm (Gulsen et al. 1995; Vander Noot and Abrahams 1998; Kapanoglu et al. 2007) is used to search the model parameters by minimising the weighted quadratic error between simulated data and target microdialyses reported in Fig. 1a–c (DA and NE dynamics in vmPFC, and DA dynamic in the NAcc, in the three different conditions reported in Pascucci et al. 2007).

Experiments run to test the model predictions: repeated stress condition

All experiments are conducted according to the Italian national law (DL 116/92) on the use of animals for research based on the European Communities Council Directive of November 24, 1986 (86/609/EEC).

## Animals

Male Sprague–Dawley rats (250–350 g; Charles River Labs, Calco, Como, Italy) are housed three to a cage with food and water ad libitum in animal facility where temperature is kept between 22 and $2 3 ~ ^ { \circ } \mathrm { C }$ and lights is on from 7.00 a.m. to $7 . 0 0 \ \mathrm { p . m }$ . Rats are allowed at least 1 week to acclimate to the colony room before any treatment. During this time rats are handled routinely. All surgeries and experiments are carried out between 11.00 a.m. and 6.00 p.m.

## Drugs

Zoletil 100 Virbac, Milano, Italy (Tiletamine HCl 50 mg/ ml ? Zolazepam HCl 50 mg/ml) and Rompun 20 Bayer $\mathbf { S } . \mathbf { p } . \mathbf { A }$ Milano, Italy (Xilazine 20 mg/ml), purchased commercially, are used as anaesthetics, and injected i.p. in a volume of 0.5 ml/kg of each drug.

## Microdialysis

Surgeries are performed 26–24 h before experiments. Rats are anaesthetized with Zoletil 100 and Rompun i.p. and mounted on a stereotaxic frame (David Kopf Instruments, Tujunga, CA) and implanted unilaterally with microdialysis probes in ipsilateral vmPFC and NAcc shell. Vertical concentric microdialysis probes (OD of 0, 31 mm) are prepared with AN69 fibres (Hospal Dasco, Bologna, Italy) according to the method of Di Chiara et al. (1993) as modified by Tanda et al. (1996). The probes are implanted vertically at the level of the vmPFC or the NAcc shell, according to the atlas of Paxinos and Watson (1998) (coordinates: vmPFC = A: ?3.7, L: 0.9 from bregma, V: -5.0 from dura; NAcc shell = A: ?1.5, L: 0.8 from bregma, V: -9.0 from dura). The length of the probes are 5 mm (membrane = 2 mm) for vmPFC and 9 mm (membrane = 2 mm) for NAcc. Each probe is fixed with epoxy glue and dental cement, and the skin is sutured. Rats are then returned to their home cages and the outlet and inlet probe tubing are protected by locally applied parafilm. The membranes are tested for in vitro recovery of DA and NE 26–24 h before the experiment. The microdialysis probe is connected to a CMA/100 pump (Carnegie Medicine, Stockholm, Sweden) through PE-20 tubing and an ultralow torque multi-channel power assist swivel (Model MCS5, Instech Laboratories, Inc., Plymouth Meeting, PA) to allow free movement. Artificial CSF (in mM: NaCl 140.0; KCl 4.0; CaCl2 1.2; MgCl2 1.0) is pumped through the dialysis probe at a constant flow rate of 2.1 ml/min.

Control non-stressed rats are tested in a breeding cage as stressed animals. Following the start of dialysis perfusion, rats are left undisturbed for approximately 2 h before the collection of baseline samples. The mean concentration of the three samples collected immediately before treatment (\10 % variation) is taken as basal concentration. All experimental groups are then subjected to restraint in a Plexiglas box (9 9 7 9 15 cm) provided with a sliding surface allowing rats to be gently handled during both restraining and releasing procedures (Puglisi-Allegra et al. 1991; Pascucci et al. 2007). The dialysate samples are collected every 20 min for 240 min. Placements are judged by methylene blue staining. Only data from rats with correctly placed probe are here reported. Twenty microliters of each dialysate sample is analysed by ultra-performance liquid chromatography (UPLC). The remaining 22 ll are kept for possible subsequent analysis. Concentrations (pg/ 20 ll) are not corrected for probe recovery.

The UPLC system consists of an Acquity UPLC (Waters Corporation, Milford, MA) apparatus coupled to an amperometric detector (model Decade II, Antec Leyden, The Netherlands) equipped by a electrochemical flow cell (VT-03, Antec Leyden) with 0.7 mm glassy carbon working electrode, mounted with a 25 mm spacer and an in situ Ag/AgCl (ISAAC) reference electrode. The electrochemical flow cell is placed immediately after a BEH C18 column (2.1 9 50 mm, 1.7 lm particle size; Waters Corporation), and set at 400 mV of potential. The column is maintained at $3 7 ~ ^ { \circ } \mathrm { C } ,$ the flow rate is 0.07 ml/min. The mobile phase is composed of 50 mM phosphoric acid, 8 mM KCl, 0.1 mM EDTA, 2.5 mM 1-octanesulfonic acid sodium salt 12 % MeOH and pH 6.0 adjusted with NaOH. Peak height produced by oxidation of NE and DA is compared with that produced by a standard. The detection limit of assay is 0.1 pg.

## Experimental protocol and statistics

Experiments start 24 h after the implantation of dialysis tubes. Animals are divided into two groups (n = 6–7). One is subjected to four daily restraint experiences of 240 min and tested for microdialysis in 240 min restraint on the day 5, 24 h after the last stressful experience. This is compared with the second group of previously unstressed animals (controls) restrained for 240 min on day 5. Surgery is carried out 4 h after the fourth daily restraint and 24 h before restraint on day 5.

Statistical analysis are always carried out on raw data (concentrations: pg/20 ll): these are presented in figures as percent changes from baseline levels (Fig. 5).

Data on the effect of restraint on NE and DA outflow in the vmPFC and NAcc are statistically analysed by two-way ANOVAs for repeated-measure (treatment as between factor: 2 levels = control, stress, and time as within factor: 13 levels = 0, 20, 40, 60, 80, 100, 120, 140, 160, 180, 200, 220, 240 min of restraint). Simple effects are assessed by one-way ANOVA at each time point. Individual betweengroup comparisons are carried out, where appropriate, by post hoc test.

Restraint produces different effects on catecholamine outflow in control animals and in previously stressed animals. Statistical analysis shows a significant treatment 9 time interaction for NE (F12, 132 = 9.74; $p < 0 . 0 0 0 1 )$ and for DA (F12, 132 = 14.71; p \ 0.0001) in vmPFC and NAcc (F12, 132 = 8.87; p \ 0.0001). Basal levels of prefrontal cortical amines and DA in the NAcc of control are not statistically different from repeatedly stressed rats.

## Results

## The dynamics of stress responses

As previously reported (Pascucci et al. 2007), restraint induces in control animals complex and time-dependent changes in catecholamine outflows in vmPFC and NAcc. Frontal-cortical NE shows a peak increase 20–40 min after stress onset, and then declines to reach basal levels 120 min later. Cortical DA, instead, shows a modest increase in the first 20–40 min of restraint that slowly declines before showing a much larger increase after 60–80 min from the beginning of the stress: it then remains significantly higher than basal levels for the whole duration of the experiment. In the NAcc, DA reaches a peak increase 20–40 min after stress onset then declines to reach levels significantly lower than baseline after 80–100 min of stress experience. Figure 3 illustrates the functioning of the model in simulating these changes.

The model provides a detailed hypothesis of the mechanisms behind these dynamics. In the initial phase of the experiment (Fig. 3a), putatively corresponding to the beginning of an active coping behavioural strategy, the stressor strongly activates both PL and OFC/ACC. This activity fosters high cortical NE release both directly and indirectly (via CeA), resulting in a general arousal of the system. PL also prevents DR responses to stress thus indirectly restraining cortical DA release. Eventually, the established self-feeding circuit involving PL–Amg–LC results in the constant removal of the tonic inhibitory activity of a population in the mlVTA, leading to a high efflux of DA into NAcc. Persistent input from the stressor triggers a learning process between IL and PL which strengthens the inhibition of PL output neurons. This process is assumed to correspond to the progressive inhibition of all active behaviours that fail to produce a desired outcome, i.e. in this context the removal of stress. As a result of this learning mechanism, the activity of PL output neurons slowly decreases, triggering a cascade effect that results in the transition to the second phase (Fig. 3b).

The progressive inhibition of PL affects all the nuclei in the self-feeding circuit it belongs to: first, the diminished activity reaching the CeA causes the vmPFC-NE to reach again pre-stress levels, further decreasing PL activity. Second, the now weak inhibition of DR makes this area capable of propagating its output towards the VTA, increasing cortical DA release.

The enhanced activity of IL resulting from increased cortical DA outflow speeds up the process of inhibition of both PL and CeA (via ITC). Furthermore, inputs from IL excite GABAergic populations within mlVTA, which are themselves no longer inhibited by the CeA: as a result, DA outflow in NAcc drops below the baseline. The effect of this complex circuitry on the dynamics of the neuromodulators is shown in Fig. 4, which presents the simulated outflows of the neuromodulators in the target areas.

The comparison between in vivo (Fig. 1a–c) and simulated (Fig. 4a–c) data shows a substantial match, suggesting the hypotheses the model is grounded on what may represent a sufficiently accurate explanation of the target phenomena. In particular, the model reproduces the main catecholamine dynamics in the sham condition as well as in the two conditions of either NE or DA depletion in vmPFC. Furthermore, the model exhibits a clear causal chain that furnishes a detailed account of the dynamics occurring during cortical depletions.

In the model, the vmPFC NE depletion causes a loss of about 10 % in the peak response of PL during the first phase, followed by the anticipation of its decrease of about 20 min. This diminished activity propagates to CeA, which is no longer able to overcome the ‘‘gate’’ created in the mlVTA by GABAergic interneuron populations. This is the main reason why NE depletion in vmPFC prevents NAcc DA from increasing during the first phase. At the same time, PL low activation slows down the IL–PL Hebbian learning process resulting in a delayed transition to the second phase.

The vmPFC DA depletion greatly diminishes the activity in IL during the whole test, slowing down IL–PL learning process and the consequent inhibition of PL activity. The stronger and more persistent activity of PL supports a higher activation of CeA and a longer accumulation of DA released in NAcc. Deprived of the excitatory effect caused by cortical DA, IL no longer shows its inhibitory effect on mlVTA, which—in the sham condition—is the cause for NAcc DA drop below baseline.

## Repeated stress condition: predictions and in vivo tests

To validate the core hypothesis of the model, we put its predictions to a test with results coming from experiments not used to tune the parameters of the model. The predictions regard the effects that a repeated experience of the restraint stressing condition, putatively causing cumulative learning within the IL–PL subsystem, might have on the outflows of the analysed catecholamines. The model relies on the hypothesis that a learning process in vmPFC is responsible for triggering a cascade effect on the subcortical areas, eventually causing the switch from active to passive coping strategies marked by the varying DA outflow in NAcc. The experiment providing the target data refers to naive rats, experiencing restraint for the first time (Pascucci et al. 2007). Thus, if the rat has already experienced restraint, it is reasonable to assume a memory of the repeated stressful experience is preserved in the vmPFC. In the model, this memory is simulated increasing the initial value of the IL–PL connection.

![](images/18760b3388578ec721bf61e6a646fe67937d684ac8d0ccc781974c80b7e7d23d.jpg)

![](images/1746f2f2791ac8e8ec2dc5c2911323f9a6e49f90d3e17e42584332c85c91395e.jpg)

![](images/e3d6932ba41c8b7bb955fb9182ef70da0efbe266917fd766b4b9319789818db1.jpg)  
Fig. 4 Simulations of the releases of the neuromodulators—cortical NE (a), cortical DA (b) and striatal DA (c)—recorded in the three conditions (sham, depletion of vmPFC NE, and depletion of vmPFC

We set the IL–PL cortical inhibitory connection to different initial values, thus capturing the effect of different intensities of previous experiences, and assumed a partial spontaneous recovery between daily experiences. The results (Fig. 5a) show an interesting discontinuity of NAcc DA dynamics during the test when the IL–PL connection value is gradually moved from above (null/short experience) to below (long experience) a critical value of about - 1 (medium experience). In particular, short experience causes a lower DA release in NAcc in the active phase, but it does not alter the timing of the passage from the active phase to the passive one. A medium experience decreases the initial DA release in NAcc to basal levels, but still leaves unaltered the timing of the passage to the second phase of coping. Finally, and notably, a long previous experience of the stressing condition causes an anticipation of the second phase.

Previous experiments (Imperato et al. 1992, 1993) have recorded DA release in NAcc during a restraint test lasting 120 min carried out after previous moderate exposures to the restraint stressing condition (5 repetitions of 60 min, one per day). The results show the absence of the initial peak of NAcc DA release (active coping phase) followed by a decrease below the baseline after 70–80 min (marking the beginning of passive coping). These results are consistent with the prediction of the model in relation to the moderate experience (Fig. 6a, medium experience). Since the parameters of the model were not tuned to produce this result, this is a first validation of a prediction of the model (cf. Alexander and Brown 2011).

Given the positive results of this first test, a new set of experiments were carried out to acquire new data in relation to the effects of a prolonged experience of the restraint condition. A series of five repetitions of 240-min restraint (see ‘‘Experiments run to test the model predictions:

DA). The parameters have been tuned to match the original data presented in Fig. 1

repeated stress condition’’ for details) has been used to produce a ‘‘long experience’’ stressing condition. Previously stressed animals show a slight increase of prefrontal NE outflow followed by a decrease below basal levels from 40 min throughout. DA in the vmPFC has a sudden substantial increase which is maintained through the experiment, except for a slight reduction in the last 60 min. In the NAcc, DA does not increase during the first 40–60 min, and it decreases progressively below basal levels from 60 min onwards.

Figure 5 shows the empirical data partially confirming predictions of the model. DA in NAcc is the most accurate prediction (Fig. 5b): it soon decreases below the basal level, clearly marking the anticipation of the passive coping phase. The series representing the dynamics of DA in vmPFC (Fig. 5d) can also be considered as a successful validation of the model’s predictions: the outflow increases immediately after the beginning of the stressing experience maintaining a release well above the baseline for the whole duration of the test. Finally, the model partially fails to accurately reproduce the dynamics of cortical NE outflow: as predicted, the empirical data (Fig. 5e) do not show the initial high response recorded in naive rats, but the model is unable to simulate the almost constant low release of this neuromodulator. The reason is that the architecture of the model is not conceived to simulate below the baseline NE outflows at any time (apart from the depletion condition). Assuming the model does not require the addition of further components to the brain areas it currently simulates, this decrease can be explained by a diminished input reaching LC: e.g. repeated exposure to the stressor might cause a further decrease of the activity in the Amg (consistently with data reported in mice by Gilabert-Juan et al. 2011), which would result in a more complex homoeostasis involving PL, Amg and LC.

Fig. 5 Predictions suggested by the model (a, c, e) and validation via in vivo data coming from new recordings of NAcc DA (b), vmPFC DA (d) and vmPFC NE (f) after 5 daily repetitions of mechanic restraint. The model shows a high degree of accuracy in predicting DA outflows in the NAcc (also including the medium experience, which matches data described in Imperato et al. 1992, 1993). It also manages to provide a less accurate but still valuable account of the DA release in the vmPFC, but it does not reproduce correctly the NE release in vmPFC  
![](images/ba4a0b14736d87d952fa1a7c6a5ad5380f5d955d3cec0f19bb210f30e12a051e.jpg)

![](images/42643a70b22a7ccb9e434c95c0d48c91d54aed033874a421e66973f9ad3c45f2.jpg)

![](images/7b65de82cbf398ae2f419df7c92cb094c49baffd830c1b67cd70c6afb3e2b3d1.jpg)

![](images/5a047ccab7202075a6bbae0496b75c10b03b94ab9192a4dc7d2c13dbfdb2fbe1.jpg)

![](images/10002494cd6b79e134c58425894c7cbaa390cc8fbe81be5fbc08adeb131f2893.jpg)

![](images/e70c2f6df3018bc597f941b3f96cf276d2010b3d35f7dabb8a2fbdbdaeaf5485.jpg)  
Fig. 6 Two untested predictions produced by the model. The mesolimbic DA release is recorded after disconnecting two neural areas of the model (blank triangle lines) and is compared with the known data characterising sham rats (filled circle lines). The disconnections affect efferent projections of either PL (a) or IL (b) and their targeted areas in the VTA

A  
![](images/6a81ae8218991466bbe193ed401985d3edce4cb8daeac7e152d591ba03b68c78.jpg)

![](images/1efdd85dee1a14ab0186d31317a47024f028ee8e8e12ed7edb37ddd51472092f.jpg)

Overall, these results are consistent with a hypothesis assuming previous experience of the same uncontrollable stressor leads to a fast appraisal of uncontrollability in the vmPFC, erasing active coping responses and causing an immediate passage to passive coping ones. Furthermore, these new data confirm the inverse correlation between cortical and limbic DA dynamics which may be well described in terms of the two competing circuits dominated by either PL or IL.

The model provides several other predictions testable in future experiments. Among these, we briefly show here the effects of two possible disconnections highlighting the core assumptions of the model in the regulation of NAcc DA. These are simulated setting the relevant connection weights to zero and leaving all other parameters of the model unaltered. The resulting dynamics are reported in Fig. 6.

The comparison between the simulated PL-VTA and IL-VTA disconnections reveals the importance of a globally inhibitory effect that vmPFC exerts on NAcc DA levels. When IL-VTA connections are removed, the simulations show a higher first response with an even more significant increase of DA in NAcc. Furthermore, this comparison allows underlying the different role played by the two cortices in causing the switch to the second phase. In particular, the IL-VTA disconnection shows a baseline DA in NAcc outflow in the second part of the simulation (Fig. 6b), entailing the absence of a passive coping phase. These dynamics, similar to the ones recorded after the cortical DA depletion (Fig. 1b), highlight the specific role played in the model by IL—and the circuitry it controls— in inhibiting NAcc DA release when its activity is sufficiently strong due to the presence of cortical DA. These predictions can be tested using combined contralateral lesions (e.g. see Coutureau et al. 2009).

## Discussion

The present model proposes a causal explanation of the neural mechanisms underlying the appraisal of controllability in the condition of long-lasting, inescapable stress. The core hypothesis assumes the learning process taking place in vmPFC is responsible for inhibition of overall activity expressed by a system pivoting on PL, Amg and cortical NE, in favour of a system involving IL, DR and cortical DA. The balance between these two systems controls the outflow of NAcc DA and therefore the motivational state and the stress coping strategy employed by the agent: high DA outflow in the NAcc drives active responses to attempt escaping (Salamone et al. 2007; Niv et al. 2007) and low DA outflow in NAcc drives passive responses and decreased overt activity (Ventura et al. 2002; Baldo and Kelley 2007; Phillips et al. 2007).

This hypothesis is consistent both with a general role ascribed to vmPFC as a key for control of hormonal and behavioural stress responses (Cabib et al. 2002; Scornaiencki et al. 2009; Maier and Watkins 2010) and with recorded data related to the catecholamine regulation of this neural region. Indeed, high cortical NE release is correlated with general arousal, as required in the face of an unknown stressful situation (Aston-Jones et al. 1999; Berridge and Waterhouse 2003), and slightly above-baseline cortical DA outflow plays an important adaptive role by preventing excessive behavioural and physiological stress reactivity (Sullivan 2004). The model assumes that a learning process in vmPFC is activated by IL due to the persistence of the stressor: IL detects the failure of the active coping attempts and progressively increases a constant inhibitory effect on PL-dominated circuitry. This is consistent with the view stating that learning processes lead to active inhibition, rather than forgetting, of those behaviours that are no longer adaptive (Quirk 2002). Several studies support the hypothesis that IL plays a key role in these inhibitory processes in its complex interplay with PL (Rhodes and Killcross 2004; Lebro´n et al. 2004; Radley et al. 2006, 2008; Van Aerde et al. 2008), while the learning process assumed in the model is consistent with recorded hypertrophy of dendrites of the vmPFC interneurons induced by inescapable stress (Gilabert-Juan et al. 2012). The subsequent shift to passive coping strategies is strengthened by the readjustment of the catecholamine outflows. First, NE in vmPFC returns to pre-stress levels, thus diminishing arousal, and second, high DA release in PFC favours processing internal information rather than external stimuli, strengthening cognitive perseverance and internal focus (Cohen et al. 2002).

The tuning of the model’s parameters has been carried out to match a set of data described in previously published experiments (Pascucci et al. 2007). On this basis the model provides a number of predictions: here we focus on those putting to a test the core hypothesis concerning the role of the vmPFC and the competition of the two described circuitries in controlling the DA outflow in NAcc. The condition of repeated restraint is particularly useful in allowing the model to simulate complex dynamics. This condition is obtained via a manipulation of the initial strength of the IL–PL inhibitory connection, considered as proportional to the amount of a residual learning (a memory) caused by the length of the agent’s previous experience with the stressing stimulus. Increasing the initial value of this connection produces an interesting discontinuous effect on NAcc DA dynamics, showing the anticipation of the second–passive– phase (marked by below-baseline NAcc DA) only occurs after the initial active response has been completely erased (Fig. 5a). The prediction about a short experience of stressing condition is confirmed by previously published experiments (Imperato et al. 1992, 1993), whereas the new experiment here reported validates the prediction concerning a long-lasting experience of the same stressor. A fair degree of accuracy also characterises the predicted dynamics of cortical DA release after long experience. It is important to highlight the model causally correlates high activity in IL-dominated circuitry (involving cortical DA) with the below-baseline release of DA in NAcc: the timing reported in the new in vivo recordings (Fig. 5b, d) are consistent with this hypothesis.

Despite the fact the model does not simulate correctly the dynamics of cortical NE release in the tested condition of repeated stress (Fig. 5e, f), these data do not falsify the model’s causal explanation of the appraisal of controllability. Indeed, even if a more comprehensive model may be required to address these new dynamics, the core hypothesis about the two competing circuitries dominated by either PL or IL is consistent with the recorded lack of NE response.

It is also interesting to point out that the implementation of the model has driven a specific hypothesis concerning the DR and its supposed asymmetrical activation of the DAergic neurons in the VTA. There is good evidence regarding connections from DR to VTA as a whole (Geisler et al. 2007; Rodaros et al. 2007; Omelchenko and Sesack 2010; Watabe-Uchida et al. 2012), but little empirical evidence in support of the fine-grained asymmetry required by the model. To shed more light on this issue it would be interesting to measure the outflow of cortical 5-HT during restraint: the model predicts 5-HT increases during the passive coping phase with a timing consistent with the highest increase characterising cortical DA release. This correlation, which has been already recorded in a different stressing condition (Bland et al. 2003a), would also support the existence of a relation between the mechanisms underlying stress coping and those responsible for learned helplessness (Maier and Watkins 2005; Amat et al. 2005; Maier and Watkins 2010). When considering this set of studies, it must be noticed that the classic yoked-shocks paradigm report conflicting results when considering the mesoaccumbens DA response to controllable and uncontrollable stress. A 1994 study reports that mice controlling shock delivery show high levels of the extracellular DA metabolite 3-methoxytyramine (3-MT), whereas their yoked counterparts show levels of 3-MT significantly lower than those of unhandled controls (Cabib and Puglisi-Allegra 1994). In contrast, a study using intracerebral microdialysis reported that both shocked and yoked rats show only a temporary increase of mesoaccumbens DA outflow (Bland et al. 2003b). Differences in the species or the method used to measure extracellular DA (DA available for transmission) cannot account for these different findings because timedependent fluctuations of NAc 3-MT tissue levels (early increase followed by decrease below basal levels) promoted by exposure to restraint or uncontrollable shock in mice are identical to the fluctuations of NAcc DA outflow measured by microdialysis in restrained rats (Puglisi-Allegra et al. 1991). Instead, the lack of similar fluctuations of NAcc DA outflow in yoked rats is well explained by different duration and quality of the stress experience. It should be pointed out that the procedure used in the rat experiment (Bland et al. 2003b) includes a progressive increase of the response requirement and of shock intensity. This test was not intended to influence the behavioural response adopted by animals facing controllable or incontrollable stress, but to promote reliable and lasting learned helplessness which requires removal of inhibition on DR 5-HT neurons by the vmPFC (Amat et al. 2005). Instead, as already discussed, coping expressed by animals exposed for the first time to unavoidable/uncontrollable stressors is dependent on NAcc DA transmission (see Cabib and Puglisi-Allegra 2012 for review). In line with this hypothesis, temporary inactivation of the vmPFC, by focal administration of the GABA agonist muscimol, does not reduce expression of active coping in rats exposed to an escapable shock but promotes expression of learned helplessness by these animals 24 h later (Amat et al. 2005).

The proposed model opens paths for further investigations. From a computational perspective, it will be useful to investigate the interactions existing between multiple neuromodulators targeting the same areas, in particular the PFC (Briand et al. 2007) so as to remove the independence between them assumed here. From a neurocognitive perspective, the model’s hypotheses regarding the putative functional roles of the various components, neuromodulators, and processes pose interesting questions. Among these, the effects of NE and DA on goal-directed behaviour and the progressive inhibition IL exerts on PL entail an action-failure detection mechanism within IL (Mannella et al. 2013). Eventually, a better understanding of IL–PL interplay and the causal mechanisms realising the appraisal of controllability may provide a fruitful framework for translational studies of disorders related to post-traumatic stress and chronic depression (cf. Milad and Quirk 2012), also considering functional homologies (Alexander and Brown 2010, 2011) and converging data recorded in primates (Drevets et al. 2008).

Acknowledgments This research was supported by the European Commission—Project IM-CLeVeR, Intrinsically Motivated Cumulative Learning Versatile Robots (Grant No. FP7-IST-IP-231722); Project ICEA, Integrating Cognition, Emotion and Autonomy (Grant No. FP6-IST-IP-027819)—and by the Wellcome Trust (Ray Dolan Senior Investigator Award 098362/Z/12/Z). The Wellcome Trust Centre for Neuroimaging is supported by core funding from the Wellcome Trust (091593/Z/10/Z).

Open Access This article is distributed under the terms of the Creative Commons Attribution License which permits any use, distribution, and reproduction in any medium, provided the original author(s) and the source are credited.

## References

Abercrombie E, Keefe K, DiFrischia D, Zigmond M (1989) Differential effect of stress on in vivo dopamine release in striatum, nucleus accumbens, and medial frontal cortex. J Neurochem 52:1655–1658

Ahn S, Phillips AG (2002) Modulation by central and basolateral amygdalar nuclei of dopaminergic correlates of feeding to satiety in the rat nucleus accumbens and medial prefrontal cortex. J Neurosci 22:10958–10965

Ahn S, Phillips AG (2003) Independent modulation of basal and feeding-evoked dopamine efflux in the nucleus accumbens and medial prefrontal cortex by the central and basolateral amygdalar nuclei in the rat. Neuroscience 116:295–305

Alexander WH, Brown JW (2010) Computational models of performance monitoring and cognitive control. Top Cogn Sci 2:658–677

Alexander WH, Brown JW (2011) Medial prefrontal cortex as an action-outcome predictor. Nat Neurosci 14:1338–1344

Amat J, Baratta MV, Paul E, Bland ST, Watkins LR, Maier SF (2005) Medial prefrontal cortex determines how stressor controllability affects behavior and dorsal raphe nucleus. Nat Neurosci 8:365–371

Anisman H, Matheson K (2005) Stress, depression, and anhedonia: caveats concerning animal models. Neurosci Biobehav Rev 29:525–546

Arnsten A (2009) Stress signalling pathways that impair prefrontal cortex structure and function. Nat Rev Neurosci 10:410–422

Aston-Jones G, Cohen JD (2005) An integrative theory of locus coeruleus-norepinephrine function: adaptive gain and optimal performance. Annu Rev Neurosci 28:403–450

Aston-Jones G, Rajkowski J, Cohen J (1999) Role of locus coeruleus in attention and behavioral flexibility. Biol Psychiatry 46:1309–1320

Baldassarre G, Mannella F, Fiore VG, Redgrave P, Gurney K, Mirolli M (2013) Intrinsically motivated action-outcome learning and goal-based action recall: a system-level bio-constrained computational model. Neural Netw 41:168–187

Baldo B, Kelley A (2007) Discrete neurochemical coding of distinguishable motivational processes: insights from nucleus accumbens control of feeding. Psychopharmacology 191:439–459

Balleine BW, Dickinson A (1998) Goal-directed instrumental action: contingency and incentive learning and their cortical substrates. Neuropharmacology 37:407–419

Barrot M, Marinelli M, Abrous D, Rouge-Pont F, Le Moal M, Piazza P (1999) Functional heterogeneity in dopamine release and in the expression of fos-like proteins within the rat striatal complex. Eur J Neurosci 11:1155–1166

Barrot M, Marinelli M, Abrous D, Rouge-Pont F, Le Moal M, Piazza P (2000) The dopaminergic hyper-responsiveness of the shell of the nucleus accumbens is hormone-dependent. Eur J Neurosci 12:973–979

Berridge CW, Waterhouse BD (2003) The locus coeruleus-noradrenergic system: modulation of behavioral state and state-dependent cognitive processes. Brain Res Rev 42:33–84

Bland ST, Hargrave D, Pepin JL, Amat J, Watkins LR, Maier SF (2003a) Stressor controllability modulates stress-induced dopamine and serotonin efflux and morphine-induced serotonin efflux

in the medial prefrontal cortex. Neuropsychopharmacology 28:1589–1596

Bland ST, Twining C, Watkins LR, Maier SF (2003b) Stressor controllability modulates stress-induced serotonin but not dopamine efflux in the nucleus accumbens shell. Synapse 49:206–208

Bojak I, Oostendorp T, Reid A, Kotter R (2003) Connecting mean field models of neural activity to EEG and fMRI data. Brain Topogr 23:139–149

Bouret S, Duvel A, Onat S, Sara S (2003) Phasic activation of locus ceruleus neurons by the central nucleus of the amygdala. J Neurosci 23:3491–3497

Briand L, Gritton H, Howe WM, Young DA, Sarter M (2007) Modulators in concert for cognition: modulator interactions in the prefrontal cortex. Prog Neurobiol 83:69–91

Cabib S, Puglisi-Allegra S (1994) Opposite responses of mesolimbic dopamine system to controllable and incontrollable aversive experiences. J Neurosci 14:3333–3340

Cabib S, Puglisi-Allegra S (2012) The mesoaccumbens dopamine in coping with stress. Neurosci Biobehav Rev 36:79–89

Cabib S, Ventura R, Puglisi-Allegra S (2002) Opposite imbalances between mesocortical and mesoaccumbens dopamine responses to stress by the same genotype depending on living conditions. Behav Brain Res 129:179–185

Cagniard B, Balsam P, Brunner D, Zhuang X (2006) Mice with chronically elevated dopamine exhibit enhanced motivation, but not learning, for a food reward. Neuropsychopharmacology 31:1362–1370

Carr DB, Sesack SR (2000) Projections from the rat prefrontal cortex to the ventral tegmental area: target specificity in the synaptic associations with mesoaccumbens and mesocortical neurons. J Neurosci 20:3864–3873

Chidlow G, Melena J, Osborne NN (2000) Betaxolol, a beta(1)- adrenoceptor antagonist, reduces Na(?) influx into cortical synaptosomes by direct interaction with Na(?) channels: comparison with other beta-adrenoceptor antagonists. Br J Pharmacol 130:759–766

Cohen JD, Braver TS, Brown JW (2002) Computational perspectives on dopamine function in prefrontal cortex. Curr Opin Neurobiol 12:223–229

Coutureau E, Killcross S (2003) Inactivation of the infralimbic prefrontal cortex reinstates goal-directed responding in overtrained rats. Behav Brain Res 146:167–174

Coutureau E, Marchand AR, Di Scala G (2009) Goal-directed responding is sensitive to lesions to the prelimbic cortex or basolateral nucleus of the amygdala but not to their disconnection. Behav Neuroci 123:443–448

Curtis A, Bello N, Connolly K, Valentino R (2002) Corticotropinreleasing factor neurones of the central nucleus of the amygdala mediate locus coeruleus activation by cardiovascular stress. J Neuroendocrinol 14:667–682

Davis M, Whalen PJ (2001) The amygdala: vigilance and emotion. Mol Psychiatry 6:13–34

Dayan P, Abbott LF (2001) Theoretical neuroscience: computational and mathematical modeling of neural systems. MIT Press Cambridge, Cambridge

Delatour B, Gisquet-Verrier P (2000) Functional role of rat prelimbicinfralimbic cortices in spatial memory: evidence for their involvement in attention and behavioural flexibility. Behav Brain Res 109:113–128

Di Chiara G, Tanda G, Frau R, Carboni E (1993) On the preferential release of dopamine in the nucleus accumbens by amphetamine: further evidence obtained by vertically implanted concentric dialysis probes. Psychopharmacology 112:398–402

Diorio D, Viau V, Meaney M (1993) The role of the medial prefrontal cortex (cingulate gyrus) in the regulation of hypothalamicpituitary-adrenal responses to stress. J Neurosci 13:3839–3847

Drevets WC, Price JL, Furey ML (2008) Brain structural and functional abnormalities in mood disorders: implications for neurocircuitry models of depression. Brain Struct Funct 213:93–118

Fellous J-M, Linster C (1998) Computational models of neuromodulation. Neural Comput 10:771–805

Fiore VG, Sperati V, Mannella F, Mirolli M, Gurney K, Firston K, Dolan RJ, Baldassarre G (2014) Keep focussing: striatal dopamine multiple functions resolved in a single mechanism tested in a simulated humanoid robot. Front Psychol Cogn Sci 5(124)

Floresco S, West A, Ash B, Moore H, Grace A (2003) Afferent modulation of dopamine neuron firing differentially regulates tonic and phasic dopamine transmission. Nat Neurosci 6:968–973

Floresco S, St Onge J, Ghods-Sharifi S, Winstanley C (2008) Corticolimbic-striatal circuits subserving different forms of cost-benefit decision making. Cogn Affect Behav Neurosci 8:375–389

Folkman S, Lazarus R, Dunkel-Schetter C, DeLongis A, Gruen R (1986) Dynamics of a stressful encounter: cognitive appraisal, coping, and encounter outcomes. J Pers Soc Psychol 50:992–1003

Fudge JL, Emiliano AB (2003) The extended amygdala and the dopamine system: another piece of the dopamine puzzle. J Neuropsychiatry Clin Neurosci 15:306–316

Fudge JL, Haber SN (2000) The central nucleus of the amygdala projection to dopamine subpopulations in primates. Neuroscience 97:479–494

Geisler S, Derst C, Veh RW, Zahm DS (2007) Glutamatergic afferents of the ventral tegmental area in the rat. J Neurosci 27:5730–5743

Gilabert-Juan J, Castillo-Gomez E, Perez-Rando M, Molto MD, Nacher J (2011) Chronic stress induces changes in the structure of interneurons and in the expression of molecules related to neuronal structural plasticity and inhibitory neurotransmission in the amygdala of adult mice. Exp Neurol 232:33–40

Gilabert-Juan J, Castillo-Gomez E, Guirado R, Molto MD, Nacher J (2012) Chronic stress alters inhibitory networks in the medial prefrontal cortex of adult mice. Brain Struct Funct 218(6): 1591–1605. doi:10.1007/s00429-012-0479-1

Gisquet-Verrier P, Delatour B (2006) The role of the rat prelimbic/ infralimbic cortex in working memory: not involved in the shortterm maintenance but in monitoring and processing functions. Neuroscience 141:585–596

Glavin GB (1985) Stress and brain noradrenaline: a review. Neurosci Biobehav Rev 9:233–243

Grace A, Floresco S, Goto Y, Lodge D (2007) Regulation of firing of dopaminergic neurons and control of goal-directed behaviors. Trends Neurosci 30:220–227

Gulsen M, Smith AE, Tate DM (1995) A genetic algorithm approach to curve fitting. Int J Prod Res 33:1911–1923

Herman J, Ostrander M, Mueller N, Figueiredo H (2005) Limbic system mechanisms of stress regulation: hypothalamo-pituitaryadrenocortical axis. Prog Neuropsychopharmacol Biol Psychiatry 29:1201–1213

Huether G, Doering S, Ruger U, Ruther E, Schussler G (1999) The stress-reaction process and the adaptive modification and reorganization of neuronal networks. Psychiatry Res 87:83–95

Imperato A, Angelucci L, Casolini P, Zocchi A, Puglisi-Allegra S (1992) Repeated stressful experiences differently affect limbic dopamine release during and following stress. Brain Res 601:333–336

Imperato A, Cabib S, Puglisi-Allegra S (1993) Repeated stressful experiences differently affect the time-dependent responses of the mesolimbic dopamine system to the stressor. Brain Res 601:333–336

Inglis F, Moghaddam B (1999) Dopaminergic innervation of the amygdala is highly responsive to stress. J Neurochem 72:1088–1094

Jackson ME, Frost AS, Moghaddam B (2001) Stimulation of prefrontal cortex at physiologically relevant frequencies inhibits dopamine release in the nucleus accumbens. J Neurochem 78:920–923

Jedema H, Grace A (2004) Corticotropin-releasing hormone directly activates noradrenergic neurons of the locus ceruleus recorded in vitro. J Neurosci 24:9703–9713

Joel D, Weiner I (1997) The connections of the primate subthalamic nucleus: indirect pathways and the open-interconnected scheme of basal ganglia-thalamocortical circuitry. Brain Res Rev 23:62–78

Kalivas P, Duffy P (1995) Selective activation of dopamine transmission in the shell of the nucleus accumbens by stress. Brain Res 675:325–328

Kapanoglu M, Koc IO, Erdogmus S (2007) Genetic algorithms in parameter estimation for non-linear regression models: an experimental approach. J Stat Comput Simul 77:851–867

Keay K, Bandler R (2001) Parallel circuits mediating distinct emotional coping reactions to different types of stress. Neurosci Biobehav Rev 25:669–678

Killcross S, Coutureau E (2003) Coordination of actions and habits in the medial prefrontal cortex of rats. Cereb Cortex 13:400–408

Koob G (2009) Brain stress systems in the amygdala and addiction. Brain Res 1293:61–75

Lammel S, Hetzel A, Hckel O, Jones I, Liss B, Roeper J (2008) Unique properties of mesoprefrontal neurons within a dual mesocorticolimbic dopamine system. Neuron 57:760–773

Lazarus R (1993) Coping theory and research: past, present, and future. Psychosom Med 55:234–247

Lebro´n K, Milad MR, Quirk GJ (2004) Delayed recall of fear extinction in rats with lesions of ventral medial prefrontal cortex. Learn Mem 11:544–548

Lewis BL, O’Donnell P (2000) Ventral tegmental area afferents to the prefrontal cortex maintain membrane potential ‘up’ states in pyramidal neurons via d(1) dopamine receptors. Cereb Cortex 10:1168–1175

Maier SF, Watkins LR (2005) Stressor controllability and learned helplessness: the roles of the dorsal raphe nucleus, serotonin, and corticotropin-releasing factor. Neurosci Biobehav Rev 29:829–841

Maier SF, Watkins LR (2010) Role of the medial prefrontal cortex in coping and resilience. Brain Res 1355:52–60

Mannella F, Gurney K, Baldassarre G (2013) The nucleus accumbens as a nexus between values and goals in goal-directed behavior: a review and a new hypothesis. Front Behav Neurosci 7(135):e1– e29

Margolis E, Lock H, Chefer V, Shippenberg T, Hjelmstad G, Fields H (2006) Kappa opioids selectively control dopaminergic neurons projecting to the prefrontal cortex. Proc Natl Acad Sci U S A 103:2938–2942

Milad MR, Quirk GJ (2012) Fear extinction as a model for translational neuroscience: ten years of progress. Annu Rev Psychol 63:129–151

Mirolli M, Mannella F, Baldassarre G (2010) The roles of the amygdala in the affective regulation of body, brain and behaviour. Connect Sci 22(3):215–245

Missale C, Nash SR, Robinson SW, Jaber M, Caron MG (1998) Dopamine receptors: from structure to function. Physiol Rev 78:189–225

Montague PR, Dolan RJ, Friston KJ, Dayan P (2012) Computational psychiatry. Trends Cogn Sci 16:72–80

Nicniocaill B, Gratton A (2007) Medial prefrontal cortical alpha1 adrenoreceptor modulation of the nucleus accumbens dopamine response to stress in Long-Evans rats. Psychopharmacology 191:835–842

Niv Y, Daw N, Joel D, Dayan P (2007) Tonic dopamine: opportunity costs and the control of response vigor. Psychopharmacology 191:507–520

Ohira H, Isowa T, Nomura M, Ichikawa N, Kimura K, Miyakoshi M, Iidaka T, Fukuyama S, Nakajima T, Yamada J (2008) Imaging brain and immune association accompanying cognitive appraisal of an acute stressor. NeuroImage 39:500–514

Omelchenko N, Sesack SR (2010) Periaqueductal gray afferents synapse onto dopamine and GABA neurons in the rat ventral tegmental area. J Neurosci Res 88:981–991

Pascucci T, Ventura R, Latagliata EC, Cabib S, Puglisi-Allegra S (2007) The medial prefrontal cortex determines the accumbens dopamine response to stress through the opposing influences of norepinephrine and dopamine. Cereb Cortex 17:2796–2804

Paxinos G, Watson C (1998) The rat brain in stereotaxic coordinates. Academic Press, New York

Peters J, Kalivas P, Quirk G (2009) Extinction circuits for fear and addiction overlap in prefrontal cortex. Learn Mem 16:279–288

Phan K, Taylor S, Welsh R, Ho S, Britton J, Liberzon I (2004) Neural correlates of individual ratings of emotional salience: a trialrelated fMRI study. Neuroimage 21:768–780

Phillips P, Walton M, Jhou T (2007) Calculating utility: preclinical evidence for cost-benefit analysis by mesolimbic dopamine. Psychopharmacology 191:483–495

Pruessner J, Dedovic K, Khalili-Mahani N, Engert V, Pruessner M, Buss C, Renwick R, Dagher A, Meaney M, Lupien S (2008) Deactivation of the limbic system during acute psychosocial stress: evidence from positron emission tomography and functional magnetic resonance imaging studies. Biol Psychiatry 63:234–240

Puglisi-Allegra S, Imperato A, Angelucci L, Cabib S (1991) Acute stress induces time-dependent responses in dopamine mesolimbic system. Brain Res 554:217–222

Quirk GJ (2002) Memory for extinction of conditioned fear is longlasting and persists following spontaneous recovery. Learn Mem 9:402–407

Quirk GJ, Mueller D (2008) Neural mechanisms of extinction learning and retrieval. Neuropsychopharmacology 33:56–72

Radley J, Arias C, Sawchenko PE (2006) Regional differentiation of the medial prefrontal cortex in regulating adaptive responses to acute emotional stress. J Neurosci 26:12967–12976

Radley JJ, Williams B, Sawchenko PE (2008) Noradrenergic innervation of the dorsal medial prefrontal cortex modulates hypothalamo-pituitary-adrenal responses to acute emotional stress. J Neurosci 28:5806–5816

Radley JJ, Gosselink KL, Sawchenko PE (2009) A discrete gabaergic relay mediates medial prefrontal cortical inhibition of the neuroendocrine stress response. J Neurosci 29:7330–7340

Rhodes SEV, Killcross AS (2004) Lesions of rat infralimbic cortex enhance recovery and reinstatement of an appetitive Pavlovian response. Learn Mem 11:611–616

Rodaros D, Caruana DA, Amir S, Stewart J (2007) Corticotropinreleasing factor projections from limbic forebrain and paraventricular nucleus of the hypothalamus to the region of the ventral tegmental area. Neuroscience 150:8–13

Room P, Russchen FT, Groenewegen HJ, Lohman AH (1985) Efferent connections of the prelimbic (area 32) and the infralimbic (area 25) cortices: an anterograde tracing study in the cat. J Comp Neurol 242:40–55

Salamone JD, Correa M, Mingote S, Weber SM (2003) Nucleus accumbens dopamine and the regulation of effort in foodseeking behavior: implications for studies of natural motivation, psychiatry, and drug abuse. J Pharmacol Exp Ther 305:1–8

Salamone JD, Correa M, Farrar A, Mingote SM (2007) Effort-related functions of nucleus accumbens dopamine and associated forebrain circuits. Psychopharmacology 191:461–482

Salomons T, Johnstone T, Backonja M, Shackman A, Davidson R (2007) Individual differences in the effects of perceived controllability on pain perception: critical role of the prefrontal cortex. J Cogn Neurosci 19:993–1003

Scornaiencki R, Cantrup R, Rushlow W, Rajakumar N (2009) Prefrontal cortical d1 dopamine receptors modulate subcortical d2 dopamine receptor-mediated stress responsiveness. Int J Neuropsychopharmacol 12:1195–1208

Sotres-Bayon F, Quirk G (2010) Prefrontal control of fear: more than just extinction. Curr Opin Neurobiol 20:231–235

Sullivan R (2004) Hemispheric asymmetry in stress processing in rat prefrontal cortex and the role of mesocortical dopamine. Stress 7:131–143

Sullivan R, Gratton A (2002) Behavioral effects of excitotoxic lesions of ventral medial prefrontal cortex in the rat are hemispheredependent. Brain Res 927:69–79

Tanda G, Bassareo V, Di Chiara G (1996) Mianserin markedly and selectively increases extracellular dopamine in the prefrontal cortex as compared to the nucleus accumbens of the rat. Psychopharmacology 123:127–130

Tavares R, Correa F, Resstel L (2009) Opposite role of infralimbic and prelimbic cortex in the tachycardiac response evoked by acute restraint stress in rats. J Neurosci Res 87:2601–2607

Tierney PL, Thierry AM, Glowinski J, Deniau JM, Gioanni Y (2008) Dopamine modulates temporal dynamics of feedforward inhibition in rat prefrontal cortex in vivo. Cereb Cortex 18:2251–2262

Ursin H, Eriksen H (2004) The cognitive activation theory of stress. Psychoneuroendocrinology 29:567–592

Valentino R, Van Bockstaele E (2001) Opposing regulation of the locus coeruleus by corticotropin-releasing factor and opioids. Potential for reciprocal interactions between stress and opioid sensitivity. Psychopharmacology 158:331–342

Van Aerde KI, Heistek TS, Mansvelder HD (2008) Prelimbic and infralimbic prefrontal cortex interact during fast network oscillations. PLoS One 3:e2725

Van Bockstaele E, Bajic D, Proudfit H, Valentino R (2001) Topographic architecture of stress-related pathways targeting the noradrenergic locus coeruleus. Physiol Behav 73:273–283

Vander Noot TJ, Abrahams I (1998) The use of genetic algorithms in the non-linear regression of immittance data. J Electroanal Chem 448:17–23

Ventura R, Cabib S, Puglisi-Allegra S (2002) Genetic susceptibility of mesocortical dopamine to stress determines liability to inhibition of mesoaccumbens dopamine and to behavioral ‘despair’ in a mouse model of depression. Neuroscience 115:999–1007

Vertes RP (1991) A PHA-L analysis of ascending projections of the dorsal raphe nucleus in the rat. J Comp Neurol 313:643–668

Vertes RP (2004) Differential projections of the infralimbic and prelimbic cortex in the rat. Synapse 51:32–58

Vidal-Gonzalez I, Vidal-Gonzalez B, Rauch SL, Quirk GJ (2006) Microstimulation reveals opposing influences of prelimbic and infralimbic cortex on the expression of conditioned fear. Learn Mem 13:728–733

Wager T, Davidson M, Hughes B, Lindquist M, Ochsner K (2008) Prefrontal-subcortical pathways mediating successful emotion regulation. Neuron 59:1037–1050

Watabe-Uchida M, Zhu L, Ogawa SK, Vamanrao A, Uchida N (2012) Whole-brain mapping of direct inputs to midbrain dopamine neurons. Neuron 74:858–873

Zhou FM, Hablitz JJ (1999) Dopamine modulation of membrane and synaptic properties of interneurons in rat cerebral cortex. J Neurophysiol 81:967–976